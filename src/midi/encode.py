"""
Convert mido midi objects representations of midifiles
"""
from __future__ import division

import numpy as np
import collections
import mido
from typing import List, Dict

import config
import errors
import midi
from midi import pitches, decode

# from midi import NoteVector, MultiTrack, Track
from utils import utils


def identity(c, m, v=0):
    """encode & decode midifiles
    (conversion is lossy)
    m :: MultiTrack | [MultiTrack]
    """
    if type(m) is list:
        return decode.tracks(c, midiFiles(c, m, v=v), v=v)
    else:
        return decode.track(c, midiFile(c, m, v=v)[0], v=v)


def midiFiles(c,
              midis: List[midi.MultiTrack],
              multiTrack=True,
              reduce_dims=midi.ReduceDimsOptions.NONE,
              velocity=None,
              dim4=True,
              split_files=False,
              v=0):
    """ Encode a list of mido.MidiFile
    reduce dims filters out unused dimensions
     'global' -> filter after all midiFiles have been encoded (keep note-structure)
     'midiFile' -> filter per midiFile, discard note structure

    dim4 adds a dimension to the output, so that the output will fit keras'
    ImageDataGenerator, with (samples, timesteps, notes, 1)
    """

    # TODO split long files in samples

    # tracks_list = [
    #     midiFile(c, mid, multiTrack, velocity, reduce_dims, split_files)
    #     for mid in midis
    # ]

    if v: config.info(multiTrack)
    n_notes = 1
    tracks = []
    for mid in midis:
        encoded_tracks = midiFile(
            c, mid, multiTrack, velocity, reduce_dims, split_files, v=v)
        for track in encoded_tracks:
            if track.n_notes() > n_notes:
                n_notes = track.n_notes()
            tracks.append(track)

    tracks_ = []
    for track in tracks:
        track = track.fit_dimensions(c.n_timesteps, n_notes)
        tracks_.append(track)

    tracks = np.array(tracks_)
    if reduce_dims == midi.ReduceDimsOptions.GLOBAL:
        tracks = midi.reduce_MultiTrack_list_dims(tracks)

    if dim4:
        return tracks.reshape(list(tracks.shape) + [1])
    return tracks


def midiFile(c,
             mid: mido.MidiFile,
             multiTrack=True,
             velocity=None,
             reduce_dims=True,
             split_files=False,
             v=0):
    """
    c :: setup.Context
    return :: [ MultiTrack ] | [ Track ]
    """
    # TODO split files
    if not isinstance(mid, mido.MidiFile):
        errors.typeError('mido.MidiFile', mid)
    # TODO # if bpm is given: 'normalize' t ?

    # matrix :: [ NoteVector per instance ]
    # all midinotes will be grouped into 1 MultiTrack per midichannel
    matrix = midi.MultiTrack(c.n_timesteps)
    if not mid.ticks_per_beat == 96:
        # e.g. 96 PPQ  # pulses per quarter note (beat)
        # TODO prevent usage of msg.time in ticks_per_beat
        if v: config.info('PPQ is not 96 but [%i]' % mid.ticks_per_beat)

    # TODO a midifile that consists of multiple tracks is interpreted
    # as multiple independent files
    if mid.type == 2:
        # type = async
        errors.typeError('mido.MidiFile.type 0 | 1', 2)
    # elif mid.type == 1:
    # TODO are multiple midichannels concatenated?
    # config.debug('WARNING', 'type not == 0')
    #     midis = mid.tracks
    # elif mid.type == 0:
    #     midis = [mid]

    t = 0
    matrix = _extend_MultiTrack(c, matrix, mid, t, velocity)
    if reduce_dims == midi.ReduceDimsOptions.MIDIFILE:
        matrix = matrix.reduce_dims()

    if multiTrack:
        return [matrix]
    # return midi.multiTrack_to_list_of_Track(matrix)
    return matrix.multiTrack_to_list_of_Track()


def _extend_MultiTrack(c, matrix: midi.MultiTrack, mid, t,
                       velocity) -> midi.MultiTrack:
    """ ...
    """

    # this auto-converts mid msgs.time to seconds
    # alternative: use
    #  for i, track in mid.tracks
    #    msg = track[index]
    for msg in mid:
        t += msg.time  # seconds for type 1,2
        i = utils.round_(t / c.dt)  # instance index (time-step)
        if not i < c.n_timesteps:
            # max t reached: return matrix
            return matrix

        matrix = msg_in_MultiTrack(c, msg, i, matrix, velocity)

    return matrix


def msg_in_MultiTrack(c,
                      msg: mido.Message,
                      i: int,
                      matrix: midi.MultiTrack,
                      use_padding: True,
                      velocity=None) -> midi.MultiTrack:
    # :velocity = None | float in range(0,1)
    if not midi.is_note_on(msg):
        return matrix

    if velocity is None:
        velocity = min(msg.velocity, midi.VELOCITY_RANGE) / float(
            midi.VELOCITY_RANGE)

    # use_padding = False
    if use_padding:
        iter1 = range(i, i + midi.PADDING)
    else:
        iter1 = [i]
    for i_ in iter1:
        if i_ < c.n_timesteps:
            vector = single_msg(msg, velocity)
            matrix[i_, ] = midi.combine_notes(matrix[i_], vector)
            velocity *= midi.VELOCITY_DECAY
    return matrix


def single_msg(msg: mido.Message, velocity=None) -> midi.NoteVector:
    # encoder mido.Message to vector
    # midi :: mido midi msg
    # TODO
    # ignore msg.velocity for now
    notes = midi.NoteVector()
    default_note = 1.
    # TODO
    # for each instance
    #   for each channel: [note], [velocity]
    if not midi.is_note_on(msg):
        return notes

    note_index = note(msg.note)
    if velocity is None:
        velocity = default_note
    # highest_note_i = midi.HIGHEST_NOTE - 1
    # normalized_note = max(min(msg.note, highest_note_i), midi.LOWEST_NOTE)
    # note_index = midi.SILENT_NOTES + normalized_note - midi.LOWEST_NOTE
    notes[note_index] = velocity
    return notes


def note(value=1):
    # return note value (1-127) or None
    for i, note_list in enumerate(midi.USED_PITCHES):
        if value in note_list:
            return midi.SILENT_NOTES + i
    return i + 1
