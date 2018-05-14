# The modules midi.encode, midi.decode depend on the following functions,
# therefore this module cannot import them

# -*- coding: utf-8 -*-
""" Midi Datastructures
Functions that have to do with midi files
Midi is represented either as mido.midi or np.array

The encoding is not lossless: the data is quantized and meta-data is discarded

Encoding & decoding (mido-np conversion)
During encoding, time is automatically converted, dependent on the meta info of the midifile
During decoding, midi-time (PPQ) is set according to the definitions in `context`.
Thus, the midi-time resolution may change during conversion.

Note-off messages are ignored during encoding, for they often are independent of the actual length of a sound. (The length/decay of the sound of the majority of percussion instruments is determined by the instrument itself, and not by the player)

Midi can be represented in numpy ndarrays, either as
  Track :: (timesteps, note)
  MultiTrack :: (timesteps, notes)

note = [0] | [1]
notes = [i] for i in range(n_notes)

"""
from __future__ import division

import numpy as np
import collections
import mido
from typing import List, Dict

import config
import errors
from utils import utils
# from . import encode
# from . import decode

SILENT_NOTES = 0  # 0: no silent notes | int: silent notes
LOWEST_NOTE = 35
HIGHEST_NOTE = 82
N_NOTES = HIGHEST_NOTE - LOWEST_NOTE + SILENT_NOTES
VELOCITY_RANGE = 127
NOTE_OFF = 'note_off'
NOTE_ON = 'note_on'
MIDI_NOISE_FLOOR = 0.5  # real values below this number will be ignored by midi decoders
PADDING = 3  # n array cells after an instance of a note-on msg (should be > 0)
VELOCITY_DECAY = 0.3  # velocity decay for every padded-cell

DTYPE = 'float32'

### from magenta.music.drums_encoder_decoder.py
# Default list of 9 drum types, where each type is represented by a list of
# MIDI pitches for drum sounds belonging to that type. This default list
# attempts to map all GM1 and GM2 drums onto a much smaller standard drum kit
# based on drum sound and function.
DEFAULT_DRUM_TYPE_PITCHES = [
    # bass drum
    [36, 35],

    # snare drum
    [38, 27, 28, 31, 32, 33, 34, 37, 39, 40, 56, 65, 66, 75, 85],

    # closed hi-hat
    [42, 44, 54, 68, 69, 70, 71, 73, 78, 80],

    # open hi-hat
    [46, 67, 72, 74, 79, 81],

    # low tom
    [45, 29, 41, 61, 64, 84],

    # mid tom
    [48, 47, 60, 63, 77, 86, 87],

    # high tom
    [50, 30, 43, 62, 76, 83],

    # crash cymbal
    [49, 55, 57, 58],

    # ride cymbal
    [51, 52, 53, 59, 82]
]


class ReduceDimsOptions:
    GLOBAL = 'global'
    MIDIFILE = 'MidiFile'
    NONE = 'none'


class NoteVector(np.ndarray):
    """ Array with floats in range [0,1] for every (midi) note
    to be used as note-on messages at an instance
    """

    # def __new__(cls, array=np.zeros(N_NOTES)):
    # note: function default args are evaluated once, before runtime

    def __new__(cls, array=None, n_notes=None):
        # array :: [ notes ] | None
        if array is None:
            if n_notes is None:
                n_notes = N_NOTES
            array = np.zeros(N_NOTES)
        return array.astype(DTYPE).view(cls)


class MultiTrack(np.ndarray):
    """ np.ndarray :: (timesteps, NoteVector),
    with length 'track-length'

    """

    def __new__(cls, n_timesteps, n_notes=None):
        if n_notes is None:
            n_notes = N_NOTES
        arr = np.zeros([n_timesteps, n_notes], dtype=DTYPE)
        # at every timestep, fill notes with index in range 0:SILENT_NOTES with 1
        arr[:, :SILENT_NOTES] = 1.
        return arr.astype(DTYPE).view(cls)

    def length_in_seconds(self):
        # n instances * dt, in seconds
        return self.n_timesteps * self.dt

    def n_timesteps(self):
        return self.shape[0]

    def n_notes(self):
        return self.shape[1]

    def multiTrack_to_list_of_Track(self):
        # return :: [ Track ]
        # matrix = array (timesteps, notes)
        tracks = []
        note_indices = self.shape[1]

        for i in range(note_indices):
            # ignore notes indices that are not present
            if self[:, i].max() > MIDI_NOISE_FLOOR:
                tracks.append(Track(self[:, i]))

        return np.stack(tracks)

    def reduce_dims(self):
        # return :: MultiTrack
        # discard note order
        # TODO parallelize
        used_indices = []
        for note_i in range(self.shape[1]):
            if self[:, note_i].max() > MIDI_NOISE_FLOOR:
                used_indices.append(note_i)
        return self[:, used_indices]

    def fit_dimensions(self, n_timesteps, n_notes):
        # increase dimensions to (n_timesteps, n_notes)
        if self.n_timesteps() < n_timesteps or self.n_notes() < n_notes:
            track = MultiTrack(n_timesteps, n_notes)
            track[:self.n_timesteps(), :self.n_notes()] = self
            return track
        return self


class Track(MultiTrack):
    """ A MultiTrack where NoteVector.length of 1
    """

    def __new__(cls, array):
        return MultiTrack.__new__(array.shape[0], n_notes=1)

    def __init__(self, array):
        # MultiTrack.__init__(array.shape[0], n_notes=1)
        if len(array.shape) == 1:
            # transform [0, 1, ..] => [[0], [1], ..]
            array = np.expand_dims(array, axis=1)
        self[:, 0] = array[:, 0]


def second2tick(c, t):
    return round(mido.second2tick(t, c.ticks_per_beat, c.tempo))


def combine_notes(v1, v2):
    # v = Notes((v1 + v2).clip(0, 1))
    v = np.maximum(v1, v2)

    if SILENT_NOTES > 0:
        # use a placeholder note to indicate the absence of a note_on msg
        # if for v1 & v2, no notes (except a SILENT_NOTE) are 1,
        #   SILENT_NOTE must be 1 else 0
        if v1[SILENT_NOTES:].max(
        ) < MIDI_NOISE_FLOOR and v2[SILENT_NOTES:].max() < MIDI_NOISE_FLOOR:
            v[:SILENT_NOTES] = 1.
        else:
            v[:SILENT_NOTES] = 0
    return v


def convert_time_to_relative_value(ls, convert_time):
    # convert in place
    current_t = 0
    prev_t = 0
    for msg in ls:
        old_t = msg.time
        if prev_t > old_t:
            config.debug('prev-t >', prev_t, old_t)
        prev_t = old_t
        if old_t < current_t:
            config.debug('old current', old_t, current_t)
        dt = old_t - current_t
        msg.time = convert_time(dt)
        current_t += dt
    return ls


def reduce_MultiTrack_list_dims(tracks):
    # [ MultiTrack ] -> [ MultiTrack ]
    used_indices = []
    for note_i in range(tracks.shape[-1]):
        if tracks[:, :, note_i].max() > MIDI_NOISE_FLOOR:
            used_indices.append(note_i)
    tracks = tracks[:, :, used_indices]
    config.info('reduced mt list dims:', tracks.shape)
    return tracks  # return tracks[:, :, indices]
