from openwakeword.model import Model
import numpy as np
import scipy.io.wavfile as wav
import os
wav.write('temp_tone.wav', 16000, np.zeros(16000, dtype=np.float32))
model = Model(wakeword_models=['app/assets/wakeword/hey_jarvis.onnx'])
print('model loaded')
os.remove('temp_tone.wav')
