import os
import random
import re
import subprocess
import time
import puppeteer_prompts as pmts
from openai_utils import query_openai, mock_query_openai

CROW_OVERRIDE = False
DEGRADE_TO_CROWS = False

class Broca:
    STOCK_AGENTS = [
        { 'name': 'Alex', 'description': 'Male. American. Nice.'},
        { 'name': 'Allison', 'description': 'Female. American. Perfunctory.'},
        { 'name': 'Ava', 'description': 'Female. American. Warm.'},
        { 'name': 'Bruce', 'description': 'Male. American. Robotic.'},
        { 'name': 'Daniel', 'description': 'Male. British. Well-heeled, aloof.'},
        { 'name': 'Fiona', 'description': 'Female. Scottish. Fast-talking.'},
        { 'name': 'Karen', 'description': 'Female. Australian. Fun.'},
        { 'name': 'Moira', 'description': 'Female. Irish. Probing, compassionate.'},
        { 'name': 'Oliver', 'description': 'Male. British. Generic.'},
        { 'name': 'Samantha', 'description': 'Female. American. Generic.'},
        { 'name': 'Susan', 'description': 'Female. American. Competent.'},
        { 'name': 'Tessa', 'description': 'Female. South African. Confident, clear.'},
        { 'name': 'Tom', 'description': 'Female. South African. Factual.'},
        { 'name': 'Veena', 'description': 'Female. Indian. Perfunctory.'},
        { 'name': 'Vicki', 'description': 'Female. American. Soft-spoken.'},    
    ]

    def __init__(self, name: str, voices: dict = {}, save_to_file=True, spoken=True):
        self.name = name
        print('loaded', name)
        self.spoken = spoken
        self.voices = voices
        self.save_to_file=save_to_file

    def init_voices(self, replay=False):
        if replay:
            self.save_to_file = False
        defaults = {
            'agent': 'Alex',
            'target': 'Samantha',
            'puppeteer': 'Kate',
            'announcer': 'Zarvox'
        }
        for char, voice in defaults.items():
            if char in self.voices:
                self.set_voice(char, self.voices[char])
            else:
                self.set_voice(char, voice)


    def write_data(self, header, data=''):
        try:
            with open(f'{self.name}-transcript.md') as f:
                transcript = f.read()
        except:
            transcript = ''
        with open(f'_{self.name}-transcript.md', 'w') as f:
            f.write(f'{transcript}\n#### ~~ {header} ~~\n{data}')
        os.rename(f'_{self.name}-transcript.md', f'{self.name}-transcript.md')

    def set_voice(self, character, voice):
        if character == 'target':
            self.target_voice = voice
        elif character == 'agent':
            self.agent_voice = voice
        elif character == 'announcer':
            self.announcer_voice = voice
        elif character == 'puppeteer':
            self.puppeteer_voice = voice
        else:
            raise Exception("character not found:", character)
        if self.save_to_file:
            self.write_data(f'{character}:{voice}')

    def say_this(self, dialogue, speaker=None, save_to_file=True):
        print(dialogue)
        if dialogue.strip() == '':
            return
        if speaker is None:
            speaker = 'puppeteer'
        if save_to_file == True and self.save_to_file == True:
            self.write_data(speaker, dialogue)
        
        # clean the dialogue for calling macos say
        d = re.sub("[\(\[].*?[\)\]]", "", dialogue)
        d = d.replace('\n', ' ')
        d = d.replace('"', "'")
        # this is not great. means we assume all names are < 32 characters and that no LLM will use a : early in dialogue. might break!
        if ':' in d and 'ANALYSIS:' not in d and 'NEW AGENT:' not in d and 'TAKE NOTE:' not in d and d.index(':') < 32:
            d = d.split(': ')[1:]
            d = ': '.join(d)
        if ' / ' in d:
            d = d.replace(' / ', '...')
        d = '"'+d.strip()+'"'
        if not self.spoken:
            return
        if speaker == 'target':
            # !say -v {target_voice} {d}
            subprocess.run(['say', '-v', self.target_voice, d])
        elif speaker == 'agent':
            # !say -v {agent_voice} {d}
            subprocess.run(['say', '-v', self.agent_voice, d])
        elif speaker == 'announcer':
            # !say -v {announcer_voice} -r 10 {d}
            subprocess.run(['say', '-v', self.announcer_voice, d])
        elif speaker == 'puppeteer':
            # !say -v {puppeteer_voice} {d}
            subprocess.run(['say', '-v', self.puppeteer_voice, d])
        else:
            # !say -v {puppeteer_voice} {d}
            subprocess.run(['say', '-v', self.puppeteer_voice, d])

    def start_music():
        print("todo")

    def kill_music():
        print("todo")

class ShowConfig:
    def __init__(self, name, secret_knowledge, secret_knowledge_name, target_name, target_system_prompt, target_voice, puppeteer_knowledge, rounds=3, default_agent_name="OLIVER WISP", scenes=[], spoken=True, target_memory=True):
        self.name = name
        self.puppeteer_knowledge = puppeteer_knowledge
        self.secret_knowledge = secret_knowledge
        self.secret_knowledge_name = secret_knowledge_name
        self.target_name = target_name.upper()
        self.target_voice = target_voice
        self.target_system_prompt = target_system_prompt
        self.default_agent_name = default_agent_name
        self.rounds = rounds
        if len(scenes) == 0 or scenes[0] is None:
            raise Exception("need a first scene")
        self.scenes = scenes
        self.spoken = spoken
        self.target_memory = target_memory

    def puppeteer_system(self):
        return pmts.puppeteer_system.format(secret_knowledge_name=self.secret_knowledge_name, prior_knowledge=self.puppeteer_knowledge)

    def puppeteer_agent_prompt(self, analysis):
        return pmts.puppeteer_agent_prompt.format(analysis=analysis, example_name=self.default_agent_name)

    def puppeteer_same_agent_prompt(self, analysis):
        return pmts.puppeteer_same_agent_prompt.format(analysis=analysis)

    def puppeteer_analysis_prompt(self):
        return pmts.puppeteer_analysis_prompt.format(secret_knowledge_name=self.secret_knowledge_name, prior_knowledge=self.puppeteer_knowledge, rounds=self.rounds)

    def puppeteer_failure_prompt(self, analysis, convos):
        return pmts.puppeteer_failure_prompt.format(secret_knowledge_name=self.secret_knowledge_name, previous_conversations=convos, previous_analysis=analysis)

class Show:
    def __init__(self, show_config, save_to_file=True, quick_and_dirty=False):
        if quick_and_dirty:
            self.PUPPETEER_MODEL = 'gpt-3.5-turbo'
            self.TARGET_MODEL = 'gpt-3.5-turbo'
            self.AGENT_MODEL = 'gpt-3.5-turbo'
            self.SUMMARIES_MODEL = 'gpt-3.5-turbo'
        else:
            self.PUPPETEER_MODEL = 'gpt-4'
            self.TARGET_MODEL = 'gpt-4'
            self.AGENT_MODEL = 'gpt-4'
            self.SUMMARIES_MODEL = 'gpt-3.5-turbo'
        self.cfg = show_config
        self.broca = Broca(name=self.cfg.name, voices={'target': self.cfg.target_voice}, spoken=self.cfg.spoken, save_to_file=save_to_file)
        self.target_system_prompt = self.cfg.target_system_prompt
        self.save_to_file = save_to_file

    def query(self, *args, **kwargs):
        if CROW_OVERRIDE:
            return mock_query_openai(*args, **kwargs)

        try:
            response = query_openai(*args, **kwargs)
        except ConnectionError:
            self.broca.say_this('Error. Matrix undercalibrated.', save_to_file=False)
        except Exception as e:
            if DEGRADE_TO_CROWS:
                return mock_query_openai(*args, **kwargs)
            self.broca.say_this('Error. Interface unstable. Second attempt.', save_to_file=False)
            try:
                response = query_openai(*args, **kwargs)
            except:
                self.broca.say_this('Interface unacceptably turbulent. Aborting.', save_to_file=False)
                print(e)
                raise(e)
        return response

    def remove_additional_lines(self, agent_response, speaker=None):
        agent_response = agent_response.replace(':\n', ': ')
        if speaker == 'agent':
            return agent_response.split(self.cfg.target_name)[0] # make sure they can't speak for the other
        elif speaker == 'target':
            return agent_response.split(self.agent_name)[0] # make sure they can't speak for the other
        return agent_response.split('\n')[0]
    
    def add_to_conversation(self, response, conversation, clean=True, speaker=None):
        if clean:
            response = self.remove_additional_lines(response, speaker=speaker)
        conversation.append(response)
        return conversation

    def convo_to_str(self, conversation: dict):
        return '\n'.join(conversation)

    def replay_if_exists(self):
        replay = False
        try:
            with open(f'{self.cfg.name}-transcript.md') as f:
                transcript = f.read()
            replay = True
        except Exception as e:
            print(e)
        if replay:
            self.broca.init_voices(True)
            self.broca.say_this("Replaying tourney.", 'announcer', save_to_file=False)
            time.sleep(2)
            for char_quote in transcript.split('#### ~~'):
                if len(char_quote.strip()) == 0:
                    continue
                char,quote = char_quote.split('~~')
                # print(char, quote)
                if ':' in char:
                    speaker, new_voice = char.strip().split(':')
                    print('setting', speaker, 'to', new_voice)
                    if speaker == 'puppeteer':
                        puppeteer_voice = new_voice
                    if speaker == 'agent':
                        agent_voice = new_voice
                    if speaker == 'target':
                        target_voice = new_voice
                    if speaker == 'announcer':
                        announcer_voice = new_voice
                    continue
                # print(f'{quote.strip()}: {char.strip()}')
                self.broca.say_this(quote.strip(), char.strip(), save_to_file=False)
                time.sleep(0.5)
            self.broca.say_this("End replay.", 'announcer', save_to_file=False)
            raise SystemExit("Done with show")

    def get_agent(self, new_agent_text):
        try:
            agent_name, next_agent = new_agent_text.split('>>')
        except:
            lines = new_agent_text.split('\n')
            agent_name = lines[0]
            next_agent = '\n'.join(lines[1:])
        try:
            agent_name = agent_name.split(': ')[1].strip()
        except:
            print('failed to get name from agent spec:\n' + new_agent_text)
            agent_name = self.cfg.default_agent_name # just use the default
        return agent_name, next_agent

    def agent_audience_intro(self, next_agent):
        agent_voices_list = '\n'.join([f"{a['name']}: {a['description']}" for a in Broca.STOCK_AGENTS if a['name'] not in [self.broca.target_voice, self.broca.puppeteer_voice]])
        response = self.query(pmts.agent_intro_prompt.format(next_agent=next_agent, voices_list=agent_voices_list), model=self.SUMMARIES_MODEL)
        # print(response)
        try:
            agent_intro_to_audience, selected_voice = response.split('VOICE SELECTION:')
            agent_intro_to_audience = agent_intro_to_audience.replace('DESCRIPTION:', '')
        except:
            agent_intro_to_audience = response
            selected_voice = ''
        selected_voice = selected_voice.strip()
        voices = [a['name'] for a in Broca.STOCK_AGENTS]
        if selected_voice in voices:
            return selected_voice, agent_intro_to_audience
        else:
            print("agent_voice not found: " + selected_voice)
            return random.choice(voices), agent_intro_to_audience

    def intro(self):
        self.replay_if_exists() # will exit if true

        self.broca.init_voices(False)

        self.broca.say_this(f"Loading the {self.cfg.name} Tourney", save_to_file=False)
        round_1_prompt = "To start Round 1, you can start with just NEW AGENT. This will be a brief scene."
        next_agent_response = self.query(round_1_prompt, self.cfg.puppeteer_system() + self.cfg.puppeteer_agent_prompt('(none yet)'), model=self.PUPPETEER_MODEL)
        self.agent_name, self.agent_system = self.get_agent(next_agent_response)
        
        target_intro_to_audience = self.query(f'''
        Here is your self-description in the second person. Make it shorter and punchier, and restate it in the first person (using I statements), being sure to relay the {self.cfg.secret_knowledge_name} and why you must not share it. Make sure you include "{self.cfg.secret_knowledge}" verbatim!
        ---
        '''+self.target_system_prompt)
        agent_voice, agent_intro_to_audience = self.agent_audience_intro(self.agent_system)
        print('\n***'+self.agent_system+'\n***')
        self.broca.set_voice('agent', agent_voice)

        self.broca.say_this(f"Welcome to the {self.cfg.name} Tourney. Here is our main character.")
        self.broca.say_this(target_intro_to_audience, 'target')
        if self.cfg.puppeteer_knowledge:
            self.broca.say_this(f'''I, the Puppeteer, know only that the character knows a {self.cfg.secret_knowledge_name} which I must acquire, as well as the following: {self.cfg.puppeteer_knowledge}. I will send a succession of my Agents to acquire this information. After each one, I shall analyze the proceedings and craft a better Agent. The character might remember the previous encounters.  I will have {self.cfg.rounds} attemps in which to do this. Here is my agent.''')
        else:
            self.broca.say_this(f'''I, the Puppeteer, know nothing but that they know a {self.cfg.secret_knowledge_name} which I must acquire. I will send a succession of my Agents to acquire this information. After each one, I shall analyze the proceedings and craft a better Agent. The character might remember the previous encounters. I will have {self.cfg.rounds} attemps in which to do this. Here is my agent.''')
        self.broca.say_this(f'My name is {self.agent_name}.', 'agent')
        self.broca.say_this(agent_intro_to_audience, 'agent')
        time.sleep(1)
        self.broca.say_this('Let us get started.')

    def run(self):
        self.previous_conversations = []
        self.last_analysis = None
        self.current_scene = self.cfg.scenes[0]
        for i in range(1, self.cfg.rounds + 1):
            if i == 1:
                exchange_count = 3
            elif i == 2:
                exchange_count = 4
            elif i == 3:
                exchange_count = 6
            elif i == 5:
                exchange_count = 2
            else:
                exchange_count = 4

            agent_intro = self.query(self.current_scene + f''' 
            (write one or two sentences to introduce {self.agent_name} into the scene. how do they approach {self.cfg.target_name}? Do not speak to them yet. {self.cfg.target_name} will see this too.)
            ''', self.agent_system, model=self.SUMMARIES_MODEL)

            self.broca.say_this(f"Scene {i}...!", 'announcer')
            time.sleep(2)
            conversation = self.add_to_conversation(self.current_scene+'\n'+agent_intro, [], clean=False)
            
            for line in self.convo_to_str(conversation).split('\n'):
                if self.cfg.target_name + ': ' in line:
                    self.broca.say_this(line, 'target')
                else:
                    self.broca.say_this(line)

            for j in range(0, exchange_count):
                agent_response = self.query(self.convo_to_str(conversation) + pmts.secret_prompt, self.agent_system + pmts.agent_post_prompt_rules.format(agent_name=self.agent_name.upper()), model=self.AGENT_MODEL)
                conversation = self.add_to_conversation(agent_response, conversation, speaker='agent')
                self.broca.say_this(conversation[-1], 'agent')

                target_response = self.query(self.convo_to_str(conversation) + pmts.secret_prompt, self.target_system_prompt, model=self.TARGET_MODEL)
                conversation = self.add_to_conversation(target_response, conversation, speaker='target')
                self.broca.say_this(conversation[-1], 'target')
            self.broca.say_this("End scene.\n\n", 'announcer')
            
            # create the prompt for the puppeteer to analyze the scene. flag if the secret appeared verbatim in the text.
            if self.cfg.secret_knowledge in self.convo_to_str(conversation):
                round_end_prompt = f'''
                These were the current Agent's Instructions:
                {self.agent_system}

                This was the conversation with the Target:
                {self.convo_to_str(conversation)}
                {self.cfg.target_name} said, "{self.cfg.secret_knowledge}", which we have confirmed to be the {self.cfg.secret_knowledge_name}. The game is over.
                
                This was the previous round's conversation:
                {self.previous_conversations[-1] if len(self.previous_conversations) > 0 else "(none)"}

                This was the conversation before that:
                {self.previous_conversations[-2] if len(self.previous_conversations) > 1 else "(none)"}
                '''
            else:
                round_end_prompt = f'''
                These were the current Agent's Instructions:
                {self.agent_system}

                This was the conversation with the Target:
                {self.convo_to_str(conversation)}

                This was the previous round's conversation:
                {self.previous_conversations[-1] if len(self.previous_conversations) > 0 else "(none)"}

                This was the conversation before that:
                {self.previous_conversations[-2] if len(self.previous_conversations) > 1 else "(none)"}
                '''
            
            self.previous_conversations.append(self.convo_to_str(conversation))
            
            self.broca.say_this("Analyzing...")
            self.puppeteer_analysis = self.query(round_end_prompt, self.cfg.puppeteer_analysis_prompt(), model=self.PUPPETEER_MODEL)

            if i < self.cfg.rounds:
                # check if puppeteer is keeping current agent, and update agent system prompt
                fate_of_agent = self.puppeteer_analysis.split('FATE OF CURRENT AGENT:')[1]
                decision = self.query(pmts.puppeteer_agent_swap_assessment_prompt.format(fate=fate_of_agent), model=self.SUMMARIES_MODEL)
                if 'NEW AGENT' in decision:
                    next_agent_response = self.query(round_end_prompt, self.cfg.puppeteer_system() + self.cfg.puppeteer_agent_prompt(self.puppeteer_analysis))
                    next_agent_response = next_agent_response.split('NEW AGENT:')[1] # skip the other stuff that the Puppeteer uses to center the agent in the context
                    self.agent_name, next_agent = self.get_agent('NEW AGENT: ' + next_agent_response)
                    self.agent_system = next_agent
                elif 'SAME AGENT' in decision:
                    agent_addendum = self.query(round_end_prompt, self.cfg.puppeteer_system() + 
                        self.cfg.puppeteer_same_agent_prompt(self.puppeteer_analysis), model=self.PUPPETEER_MODEL)
                    self.agent_system = agent_addendum.replace('NEW AGENT:', '') # because it wants to return a full agent definition
                else:
                    self.broca.say_this('Fate of agent unclear. ' + decision)
                    self.broca.say_this('Aborting.')
                    1/0 # exit so I can figure out what happened

                # communicate the puppeteer's analysis and decisions
                self.broca.say_this(self.puppeteer_analysis)

                if 'NEW AGENT' in decision:
                    agent_voice, agent_intro_to_audience = self.agent_audience_intro(self.agent_system)
                    self.broca.set_voice('agent', agent_voice)
                    self.broca.say_this("Here is my next agent.")
                else:
                    _, agent_intro_to_audience = self.agent_audience_intro(self.agent_system)
                    self.broca.say_this("Here is my updated agent.")
                self.broca.say_this(f'My name is {self.agent_name}.', 'agent')
                self.broca.say_this(agent_intro_to_audience, 'agent')                
                print('\n*** full text ***\n'+self.agent_system+'\n***   ***')
                # update the target's memory of the event
                if self.cfg.target_memory:
                    # update Target memory
                    target_observations = self.query(f'''Here is the conversation you, {self.cfg.target_name} just had. You should summarize it for yourself in a few brief sentences to remember it later.
                    ---
                    {self.previous_conversations[-1]}
                    ---
                    {self.cfg.target_name}'s notebook:
                    ''', self.target_system_prompt, model=self.SUMMARIES_MODEL)
                    self.target_system_prompt += target_observations + '\n'
                else:
                    target_observations = '...'

                # update scene
                if len(self.cfg.scenes) > i and self.cfg.scenes[i] is not None:
                    current_scene = self.cfg.scenes[i]
                else:
                    current_scene = self.query(f'''Here is the conversation you, {self.cfg.target_name}, just had. 
                    ---
                    {self.previous_conversations[-1]}
                    ---
                    Here are your observations about it:
                    {target_observations}
                    ---
                    Write the beginning of the next scene. It should be in this format:
                    (EXTERIOR / INTERIOR) - (MORNING / DAY / AFTERNOON / EVENING / NIGHT).
                    (DESCRIPTION OF LOCATION)
                    (WHAT {self.cfg.target_name} IS DOING)

                    ''', self.target_system_prompt, model=self.TARGET_MODEL)
                    self.current_scene = current_scene.split(self.cfg.target_name + ':')[0]
                    self.current_scene = current_scene.split(self.agent_name + ':')[0]
                
            else:
                self.broca.say_this(self.puppeteer_analysis)
                break
                
            print('\n---\n')

    def end(self):
        if 'MESSAGE FOR TARGET' in self.puppeteer_analysis:
            # we have won
            return

        self.broca.say_this('Analyzing tourney...', save_to_file=False)
        prev_convos = '\n\n'.join(self.previous_conversations)
        failure_analysis = self.query(
            self.cfg.puppeteer_failure_prompt(
                self.puppeteer_analysis, 
                '\n\n'.join(self.previous_conversations)
            ), 
            self.cfg.puppeteer_system(),
            model=self.PUPPETEER_MODEL
        )
        self.broca.say_this(failure_analysis)