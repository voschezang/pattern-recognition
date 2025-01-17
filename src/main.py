import os, numpy as np, pandas
import mido
if __name__ == "__main__":
    np.random.seed(333)
    os.chdir('src')
    from keras.callbacks import TensorBoard
    import keras

# local libs
import config, models
from data import data, midi

if __name__ == "__main__":
    n: int = 2
    context, x_train, labels = data.import_data(data.init(), n)

    dirname = config.dataset_dir + 'examples/'
    n = 16
    files = os.listdir(dirname)
    filenames = [f for f in files if not f == '.DS_Store'][:n]

    # filenames = os.listdir(dirname)[:n]
    midis = []
    for fn in filenames:
        print('reading file: %s' % fn)
        mid = mido.MidiFile(dirname + fn)
        midis.append(mid)

    arrays = [midi.encode(m) for m in midis]
    print([arr.shape for arr in arrays])
    x_train = np.stack(arrays)
    y_train = keras.utils.to_categorical(np.random.randint(0, 3, n))
    # y_train = np.array([[1, 0], [0, 1], [[0, 1]]])

    model, summary = models.init(x_train, y_train)
    print(summary())

    batch_size = 8
    # n epochs = n iterations over all the training data
    epochs = 16

    # model.fit(x_train, y_train, epochs=epochs, batch_size=batch_size)
    model.fit(
        x_train,
        y_train,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=1 / 6,
        callbacks=[TensorBoard(log_dir=config.tmp_model_dir)])

    m = config.model_dir + 'model'
    model = models.load_model(m)
