
import whisper
import speech_recognition as sr
import subprocess
model = whisper.load_model("small.en")
r = sr.Recognizer()

def listen(limit_sec=10):
    fname = record(limit_sec)
    return model.transcribe("temp.wav", fp16=False)['text']

def record(limit_sec=10, fname='temp.wav'):
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source)
        subprocess.run(['afplay', '/System/Library/Sounds/Blow.aiff'])
        # !afplay /System/Library/Sounds/Blow.aiff
        audio = r.listen(source, timeout=5, phrase_time_limit=limit_sec)
        subprocess.run(['afplay', '/System/Library/Sounds/Bottle.aiff'])
        # !afplay /System/Library/Sounds/Bottle.aiff
    with open(fname, 'wb') as f:
        f.write(audio.get_wav_data())
    return fname