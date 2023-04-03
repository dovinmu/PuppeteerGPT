from datetime import datetime
import requests
import json
import os
from pathlib import Path
import random

SERVER_ERROR = "server_error"

with open('openai-keys.json') as f:
    openai = json.loads(f.read())
    OPENAI_API_KEY=openai['key']
    
models = {
    'paragraph-tag':  'gpt-4',
    'paragraph-summary': 'gpt-4'
}
MODEL = "gpt-3.5-turbo"

def query_openai_chat(chat: list, system: str, model=MODEL, max_tokens=300, debug=False, debug_system=False, temp=1.1, log=True):
    if log:
        write_to_log(f'<sys>\n{prompt_system}\n<pmt>\n{prompt}\n{model} {max_tokens} {temp}\n</sys>')
    # April 1, 2023 version
    endpoint = 'v1/chat/completions'
    prompt =  { "messages": [ { "role": "system", "content": prompt_system }, { "role": "user", "content": prompt } ]}
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENAI_API_KEY}'
    }
    data = {"model": model, **prompt,
            "temperature": temp, 
            "max_tokens": max_tokens
    }
    if debug:
        if debug_system:
            print("~ system prompt:", prompt['messages'][0]['content'])
        print("~ prompt:", prompt['messages'][1]['content'])
    r = requests.post(f'https://api.openai.com/{endpoint}', headers=headers, json=data)
    j = r.json()
    try:
        if 'chat' in endpoint:
            a = j['choices'][0]['message']['content']
        else:
            a = j['choices'][0]['text'].strip()
    except Exception as e:
        if log:
            write_to_log(f'<err>\n{e}\n{j}\n</err>')
        print(j)
        raise(e)
    if debug:
        print("~ response:", a, "\n~")
    if log:
        write_to_log(f'<res>\n{a}\n</res>')
    return a

def query_openai(prompt: str, prompt_system: str = '', model = "default", max_tokens=350, debug=False, debug_system=False, temp=1.1, log=True):
    if log:
        write_to_log(f'<sys>\n{prompt_system}\n</sys>\n<pmt>\n{prompt}\n</pmt>\n{model} {max_tokens} {temp}\n')
    # March 17, 2023 version
    if model == "default":
        model = MODEL
    if model in set('gpt-4, gpt-4-0314, gpt-4-32k, gpt-4-32k-0314, gpt-3.5-turbo, gpt-3.5-turbo-0301'.split(', ')):
        endpoint = 'v1/chat/completions'
        prompt =  { "messages": [ { "role": "system", "content": prompt_system }, { "role": "user", "content": prompt } ]}
    else:
        if log:
            write_to_log(f'<err>\n"only chat completions supported"')
        raise Error("only chat completions supported")
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENAI_API_KEY}'
    }
    data = {"model": model, **prompt,
            "temperature": temp, 
            "max_tokens": max_tokens
    }
    if debug:
        if debug_system:
            print("~ system prompt:", prompt['messages'][0]['content'])
        print("~ prompt:", prompt['messages'][1]['content'])
    r = requests.post(f'https://api.openai.com/{endpoint}', headers=headers, json=data)
    j = r.json()
    try:
        if 'chat' in endpoint:
            a = j['choices'][0]['message']['content']
        else:
            a = j['choices'][0]['text'].strip()
    except Exception as e:
        if log:
            write_to_log(f'<err>\n{e}\n{j}</err>')
        print(j)
        raise(e)
    if debug:
        print("~ response:", a, "\n~")
    if log:
        write_to_log(f'<res>\n{a}\n</res>')
    return a

def mock_query_openai(prompt: str, prompt_system: str = '', model = "default", max_tokens=500, debug=False, debug_system=False, temp=1.1, log=True):
    return "caw! " * random.randint(1, 4)

def write_to_log(s):
    dt = datetime.now()
    fname = f'{dt.year}-{dt.month}-{dt.day}.log'
    
    try:
        with open(fname) as f:
            txt = f.read()
    except:
        txt = ''
    with open(f'_{fname}', 'w') as f:
        f.write(f'{txt}\n{dt}\n{s}')
    os.rename(f'_{fname}', f'{fname}')