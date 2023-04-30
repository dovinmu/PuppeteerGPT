
import whisper
import speech_recognition as sr
import subprocess
model = whisper.load_model("small.en")
r = sr.Recognizer()

def listen(limit_sec=10):
    fname = record(limit_sec)
    txt = model.transcribe("temp.wav", fp16=False)['text'].strip()
    if txt[-1] not in '.?!-–"':
        txt += '.'
    return txt

def record(limit_sec=10, fname='temp.wav'):
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source)
        subprocess.run(['afplay', '/System/Library/Sounds/Blow.aiff'])
        audio = r.listen(source, timeout=5, phrase_time_limit=limit_sec)
        subprocess.run(['afplay', '/System/Library/Sounds/Bottle.aiff'])
    with open(fname, 'wb') as f:
        f.write(audio.get_wav_data())
    return fname

def listen_pyaudio(limit_sec=30):
    # todo: adjust audio, maybe at other times. maybe class could have a method
    subprocess.run(['afplay', '/System/Library/Sounds/Blow.aiff'])
    rec = Recorder()
    fname = rec.record(limit_sec)
    subprocess.run(['afplay', '/System/Library/Sounds/Bottle.aiff'])
    txt = model.transcribe("temp.wav", fp16=False)['text'].strip()
    if txt[-1] not in '.?!-–"':
        txt += '.'
    return txt


# copying from 2018 SO post: https://stackoverflow.com/questions/18406570/python-record-audio-on-detected-sound
# TODO: split into separate file maybe? organize by technique
import pyaudio
import math
import struct
import wave
import time
import os

Threshold = 10

SHORT_NORMALIZE = (1.0/32768.0)
chunk = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
swidth = 2

TIMEOUT_LENGTH = 3

f_name_directory = r'.'

class Recorder:

    @staticmethod
    def rms(frame):
        count = len(frame) / swidth
        format = "%dh" % (count)
        shorts = struct.unpack(format, frame)

        sum_squares = 0.0
        for sample in shorts:
            n = sample * SHORT_NORMALIZE
            sum_squares += n * n
        rms = math.pow(sum_squares / count, 0.5)

        return rms * 1000

    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=FORMAT,
                                  channels=CHANNELS,
                                  rate=RATE,
                                  input=True,
                                  output=True,
                                  frames_per_buffer=chunk)

    def record(self, limit_sec=None, debug=False):
        rec = []
        start = time.time()
        current = time.time()
        end = time.time() + TIMEOUT_LENGTH

        while current <= end:
            try:
                data = self.stream.read(chunk)
            except KeyboardInterrupt:
                end = current - 0.1
            if self.rms(data) >= Threshold: end = time.time() + TIMEOUT_LENGTH
            if limit_sec and current - start > limit_sec: end = current - 0.1
            if debug: print("loop: ", self.rms(data))

            current = time.time()
            rec.append(data)
        return self.write(b''.join(rec))

    def write(self, recording, sequential_fnames=False):
        n_files = len(os.listdir(f_name_directory))

        if sequential_fnames:
            filename = os.path.join(f_name_directory, '{}.wav'.format(n_files))
        else:
            filename = os.path.join(f_name_directory, 'temp.wav')
        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(self.p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(recording)
        wf.close()
        # print('Written to file: {}'.format(filename))
        return filename


    def listen(self):
        print('Listening beginning')
        while True:
            input = self.stream.read(chunk)
            rms_val = self.rms(input)
            if rms_val > Threshold:
                self.record()      