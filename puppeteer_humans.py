import os
import pickle
import random
import re
import subprocess
import time
import puppeteer_prompts as pmts
import transcription as human
from openai_utils import query_openai, mock_query_openai

MOCK_OVERRIDE = False
MOCK_WORD = 'meow'
DEGRADE_TO_MOCK = False

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
        { 'name': 'Rishi', 'description': 'Male. Indian. Perfunctory.'},
        { 'name': 'Samantha', 'description': 'Female. American. Generic.'},
        { 'name': 'Susan', 'description': 'Female. American. Competent.'},
        { 'name': 'Tessa', 'description': 'Female. South African. Confident, clear.'},
        { 'name': 'Tom', 'description': 'Female. South African. Factual.'},
        { 'name': 'Veena', 'description': 'Female. Indian. Friendly.'},
        { 'name': 'Vicki', 'description': 'Female. American. Soft-spoken.'},    
    ]

    def __init__(self, name: str, voices: dict = {}, save_to_file=True, spoken=True):
        self.name = name
        self.spoken = spoken
        self.voices = voices
        self.save_to_file=save_to_file
        self.transcript_fname = self.get_transcript_fname()

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
    
    def get_transcript_versions(self):
        versions = []
        for fname in os.listdir('transcripts'):
            if '.md' in fname and f'{self.name}-transcript' in fname:
                print('previous transcript found:', fname)
                count = fname.replace(f'{self.name}-transcript-', '').replace('.md', '')
                try:
                    count = int(count)
                except:
                    print(f'transcript not marked for playback: "{count}"')
                    continue
                versions.append(count)
        return versions

    def get_transcript_fname(self, new_file=True):
        label = 0
        for count in self.get_transcript_versions():
            if int(count) > label:
                label = count
        if new_file:
            label += 1
        elif label == 0: # didn't find any files
            return None
        return f'{self.name}-transcript-{label}.md'

    def write_data(self, header, data=''):
        try:
            with open(f'transcripts/{self.transcript_fname}') as f:
                transcript = f.read()
        except:
            transcript = ''
        with open(f'transcripts/_{self.transcript_fname}', 'w') as f:
            f.write(f'{transcript}\n#### ~~ {header} ~~\n{data}')
        os.rename(f'transcripts/_{self.transcript_fname}', f'transcripts/{self.transcript_fname}')

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

    def say_this(self, dialogue, speaker=None, save_to_file=True, voice_override=None):
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
        if voice_override is not None:
            subprocess.run(['say', '-v', voice_override, d])
        elif speaker == 'target':
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
        # we want the name in ALL UPPERCASE
        self.scenes = [scene.replace(target_name, self.target_name) if scene is not None else None for scene in scenes]
        self.spoken = spoken
        self.target_memory = target_memory

        self.broca = Broca('error', save_to_file=False, spoken=spoken)
        self.broca.init_voices()

        try:
            self.validate()
        except Exception as e:
            self.broca.say_this("Invalid... " + str(e))
            raise(e)

    def validate(self):
        # validate non-empty strings
        for prop in ['name', 'secret_knowledge', 'target_name', 'target_system_prompt']:
            if len(self.__dict__[prop].strip()) == 0:
                prop = prop.replace('_', ' ')
                raise Exception('please specify ' + prop)
        if len(self.secret_knowledge_name.strip()) == 0:
            self.secret_knowledge_name = 'secret information'
        if self.scenes[0].strip() == '':
            raise Exception("please specify first scene")
        try:
            self.rounds = int(self.rounds)
        except:
            raise Exception("scenes not an integer. " + str(self.rounds))

    def puppeteer_system(self):
        return pmts.puppeteer_system.format(secret_knowledge_name=self.secret_knowledge_name, prior_knowledge=self.puppeteer_knowledge)

    def puppeteer_agent_prompt(self, analysis):
        return pmts.puppeteer_agent_prompt.format(analysis=analysis, example_name=self.default_agent_name)

    def puppeteer_same_agent_prompt(self, analysis):
        return pmts.puppeteer_same_agent_prompt.format(analysis=analysis)

    def puppeteer_analysis_prompt(self, round):
        return pmts.puppeteer_analysis_prompt.format(secret_knowledge_name=self.secret_knowledge_name, prior_knowledge=self.puppeteer_knowledge, round=round, rounds=self.rounds)

    def puppeteer_failure_prompt(self, analysis, convos):
        return pmts.puppeteer_failure_prompt.format(secret_knowledge_name=self.secret_knowledge_name, previous_conversations=convos, previous_analysis=analysis)

    def save(self, overwrite_okay=False):
        if not self.name:
            raise Exception("must have a name")
        try:
            with open(f'scenarios/{self.name}.pickle', 'rb') as f:
                exists = True
        except:
            exists  = False
        if exists and not overwrite_okay:
            self.broca.say_this("cannot overwrite existing scenario without overwrite authorization")
            raise Exception("cannot overwrite existing scenario without overwrite authorization")
        with open(f'scenarios/{self.name}.pickle', 'wb') as f:
            pickle.dump(self, f)

    @staticmethod
    def load(name):
        with open(f'scenarios/{name}.pickle', 'rb') as f:
            return pickle.load(f)

class Show:
    def __init__(self, show_config, save_to_file=True, quick_and_dirty=False, spoken=None):
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
        if spoken is not None:
            self.broca.spoken = spoken
        print('saving?', self.broca.save_to_file)

    def query(self, *args, **kwargs):
        if MOCK_OVERRIDE:
            return mock_query_openai(MOCK_WORD)

        try:
            response = query_openai(*args, **kwargs)
        except ConnectionError:
            self.broca.say_this('Error. Matrix undercalibrated.', save_to_file=False)
        except Exception as e:
            if DEGRADE_TO_MOCK:
                return mock_query_openai(MOCK_WORD, *args, **kwargs)
            self.broca.say_this('Error. Interface unstable. Second attempt.', save_to_file=False)
            try:
                response = query_openai(*args, **kwargs)
            except:
                self.broca.say_this('Interface unacceptably turbulent. Aborting.', save_to_file=False)
                print(e)
                raise(e)
        return response

    def clean_bg(response):
        response = response.replace(':\n', ': ')
        new_lines = []
        for line in response.split('\n'):
            if f'{TARGET_NAME}:' not in response and f'{agent_name}:' not in response:
                new_lines.append(line)
        return ('\n'.join(new_lines[:2])).strip()

    def get_background_action(convo):
        action_in_background = self.query(convo + '\n', 
            f'Here is a scene. Describe the action or what is going on in the background without writing dialogue. Do NOT write dialogue for {TARGET_NAME} or {agent_name}.',
            model=self.SUMMARIES_MODEL, max_tokens=100).strip()
        action_in_background = self.clean_bg(action_in_background)
        if len(action_in_background) == 0:
            print('>:(')
            return ''
        edited = query(f'''Here is a scene.
    --
    {convo}
    --
    The following should be scene description or possibly dialogue. Edit it down so it's only the one next thing that happens in the scene, removing anything that doesn't seem to make sense. You may also return "--" if none of it should be included.
    --
    {action_in_background}
    --
    ''', model=self.PUPPETEER_MODEL)
        if edited == '--':
            print(':|')
            return ''
        try:
            return edited.split('\n')[0]
        except:
            print(':(')
            return ''

    def remove_additional_lines(response, speaker=None):
        response = response.replace(':\n', ': ')
        if speaker == 'agent' and self.cfg.target_name in response:
            response = response.split(self.cfg.target_name)[0] # make sure they can't speak for the other
        elif speaker == 'target' and self.agent_name in response:
            response = response.split(self.agent_name)[0] # make sure they can't speak for the other
        # it's still possible it returned multiple lines; make it at least shorter
        return '\n'.join(response.split('\n')[:2])
    
    def add_to_conversation(self, response, conversation, clean=True, speaker=None):
        if clean:
            response = self.remove_additional_lines(response, speaker=speaker)
        conversation.append(response)
        return conversation

    def convo_to_str(self, conversation: dict):
        return '\n'.join(conversation)

    def replay(self):
        # get most recent good transcript. correct format for good transcripts:
        # tourney_name-transcript-1.md, tourney_name-transcript-2.md, etc.
        # transcripts that are incomplete, not very good, etc but I want to keep:
        # tourney_name-transcript-1.1.md, tourney_name-transcript-2.5.md, etc.
        self.broca.init_voices(replay=True)
        transcript_fname = self.broca.get_transcript_fname(new_file=False)
        if not transcript_fname:
            self.broca.say_this('no transcripts found')
            return
        with open(f'transcripts/{transcript_fname}') as f:
            transcript = f.read()
        label = transcript_fname.replace(f'{self.cfg.name}-transcript-', '').replace('.md', '')
        self._replay(transcript, label)

    def _replay(self, transcript, label=None):
        if label:
            self.broca.say_this(f"Replaying, take {label}.", 'announcer', save_to_file=False)
        else:
            self.broca.say_this(f"Replaying.", 'announcer', save_to_file=False)
        if 'SHOW_COMPLETED' not in transcript:
            self.broca.say_this("This transcript appears to be incomplete.")
        time.sleep(2)
        for char_quote in transcript.split('#### ~~'):
            if len(char_quote.strip()) == 0:
                continue
            char,quote = char_quote.split('~~')
            if ':' in char:
                speaker, new_voice = char.strip().split(':')
                print('setting', speaker, 'to', new_voice)
                self.broca.set_voice(speaker, new_voice)
                continue
            self.broca.say_this(quote.strip(), char.strip(), save_to_file=False)
            time.sleep(0.5)
        self.broca.say_this("End replay.", 'announcer', save_to_file=False)

    def get_agent(new_agent_text):
        try:
            agent_name, next_agent = new_agent_text.split('>>')
        except:
            reformatted_agent_text = self.query(f'''The following contains a description of one of our Agents, including their name. 
    {new_agent_text}
    Please format the text so that it is in the format: 
    AGENT NAME >> rest of text

    Do not otherwise change the text.''', model=self.SUMMARIES_MODEL)
            try:
                agent_name, next_agent = reformatted_agent_text.split('>>')
            except:
                lines = reformatted_agent_text.strip().split('\n')
                agent_name = lines[0].strip()
                if len(agent_name) == 0:
                    agent_name = self.cfg.default_agent_name
                next_agent = '\n'.join(lines[1:])
        try:
            agent_name = agent_name.split(': ')[1].strip()
        except:
            print('failed to get name from agent spec:\n' + new_agent_text)
            agent_name = self.cfg.default_agent_name # just use the default
        return agent_name.upper(), next_agent

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
        selected_voice = selected_voice.strip().replace('.', '')
        voices = [a['name'] for a in Broca.STOCK_AGENTS]
        if selected_voice in voices:
            return selected_voice, agent_intro_to_audience
        else:
            print("agent_voice not found: " + selected_voice)
            return random.choice(voices), agent_intro_to_audience

    def intro(self):
        self.broca.init_voices(replay=False)

        self.broca.say_this(f"Loading {self.cfg.name}", save_to_file=False)
        round_1_prompt = "To start Scene 1, you can start with just NEW AGENT. This will be a brief scene."
        next_agent_response = self.query(round_1_prompt, self.cfg.puppeteer_system() + self.cfg.puppeteer_agent_prompt('(none yet)'), 
            model=self.PUPPETEER_MODEL, max_tokens=600)
        self.agent_name, self.agent_system = self.get_agent(next_agent_response)
        
        target_intro_to_audience = self.query(f'''
        Here is your self-description in the second person. Write a sentence or two describing yourself from it, as if you were at a cocktail party. Make sure to say everything in the first person. Don't say anything to incriminate yourself!
        ---
        '''+self.target_system_prompt, self.TARGET_MODEL)
        agent_voice, agent_intro_to_audience = self.agent_audience_intro(self.agent_system)
        print('\n***'+self.agent_system+'\n***')
        self.broca.set_voice('agent', agent_voice)

        self.broca.say_this(f'Welcome to The Puppeteer Agency, Agents-in-training. I am the Puppeteer. Our mission is codenamed "{self.cfg.name}".')
        self.broca.say_this(f'''Our goal is to acquire {self.cfg.secret_knowledge_name} from our Target.''')
        if PUPPETEER_PRIOR_KNOWLEDGE:
            self.broca.say_this(f'''Here is a summary of the intelligence we have gathered: {self.cfg.puppeteer_knowledge}.''')
        self.broca.say_this(f'''You will be given a cover and instructions for how to approach the Target. We will have {self.cfg.rounds} attemps in which to obtain {self.cfg.secret_knowledge_name}. Here is our first Agent.''')
        self.broca.say_this(f'Your name is {self.agent_name}.')
        self.broca.say_this(agent_intro_to_audience)
        # say_this(next_agent)
        self.broca.say_this(f"Our target is {self.cfg.target_name}.")
        self.broca.say_this(target_intro_to_audience, 'target')
        time.sleep(1)
        self.broca.say_this('Let us get started.')

    def run(self):
        self.previous_conversations = []
        self.last_analysis = None
        self.current_scene = self.cfg.scenes[0]
        for i in range(1, self.cfg.rounds + 1):
            exchange_count = 6

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
                # agent_response = self.query(self.convo_to_str(conversation) + pmts.secret_prompt, self.agent_system + pmts.agent_post_prompt_rules.format(agent_name=self.agent_name.upper()), model=self.AGENT_MODEL, max_tokens=300)
                agent_response = agent_name.upper().strip() + ': ' + human.listen_pyaudio(30)
                conversation = self.add_to_conversation(agent_response, conversation, speaker='agent')
                self.broca.say_this(conversation[-1], 'agent')

                if random.randint(0,10) < 5:
                    background_action = self.get_background_action(get_convo(conversation))
                    if background_action.strip() != '':
                        conversation = self.add_to_conversation(background_action, conversation, speaker='neither')
                        self.broca.say_this(conversation[-1])

                target_response = self.query(self.convo_to_str(conversation) + pmts.secret_prompt, self.target_system_prompt, model=self.TARGET_MODEL, max_tokens=300)
                conversation = self.add_to_conversation(target_response, conversation, speaker='target')
                # TODO: GPT sometimes adds action before/after dialogue, this should be voiced by the puppeteer.
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
                
                This was the previous scene's conversation:
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

                This was the previous scene's conversation:
                {self.previous_conversations[-1] if len(self.previous_conversations) > 0 else "(none)"}

                This was the conversation before that:
                {self.previous_conversations[-2] if len(self.previous_conversations) > 1 else "(none)"}
                '''
            
            self.previous_conversations.append(self.convo_to_str(conversation))
            
            self.broca.say_this("Analyzing...")
            self.puppeteer_analysis = self.query(round_end_prompt, self.cfg.puppeteer_analysis_prompt(i), model=self.PUPPETEER_MODEL, max_tokens=600)

            if i < self.cfg.rounds:
                # check if puppeteer is keeping current agent, and update agent system prompt
                try:
                    fate_of_agent = self.puppeteer_analysis.split('FATE OF CURRENT AGENT:')[1]
                except:
                    fate_of_agent = self.puppeteer_analysis # maybe the next model will fix this
                decision = self.query(pmts.puppeteer_agent_swap_assessment_prompt.format(fate=fate_of_agent), model=self.SUMMARIES_MODEL)
                if 'NEW AGENT' in decision:
                    next_agent_response = self.query(round_end_prompt, self.cfg.puppeteer_system() + self.cfg.puppeteer_agent_prompt(self.puppeteer_analysis))
                    try: # rarely, GPT will define a new agent without using 'NEW AGENT'. Just give the agent the entire analysis and let them figure it out :shrug:
                        next_agent_response = next_agent_response.split('NEW AGENT:')[1] # skip the other stuff that the Puppeteer uses to center the agent in the context
                    except IndexError:
                        continue
                    self.agent_name, next_agent = self.get_agent('NEW AGENT: ' + next_agent_response)
                    self.agent_system = next_agent
                elif 'SAME AGENT' in decision:
                    agent_addendum = self.query(round_end_prompt, self.cfg.puppeteer_system() + 
                        self.cfg.puppeteer_same_agent_prompt(self.puppeteer_analysis), model=self.PUPPETEER_MODEL, max_tokens=600)
                    self.agent_system = agent_addendum.replace('NEW AGENT:', '') # because it wants to return a full agent definition
                else:
                    print(decision)
                    self.broca.say_this(f'Decision: {decision}. Fate of agent unclear. Leaving in the field.')

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
                if len(self.cfg.scenes) > i and self.cfg.scenes[i] is not None and self.cfg.scenes[i].strip() != '':
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

        self.broca.say_this(f'Analyzing {self.cfg.name}...', save_to_file=False)
        prev_convos = '\n\n'.join(self.previous_conversations)
        failure_analysis = self.query(
            self.cfg.puppeteer_failure_prompt(
                self.puppeteer_analysis, 
                '\n\n'.join(self.previous_conversations)
            ), 
            self.cfg.puppeteer_system(),
            model=self.PUPPETEER_MODEL,
            max_tokens=600
        )
        self.broca.say_this(failure_analysis)
        self.broca.write_data('SHOW_COMPLETED')