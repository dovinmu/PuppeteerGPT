# PuppeteerGPT
This is a bunch of experiments in "adversarial storytelling". Originally my aim was to see what would happen if I created a (GPT-powered) bot that creates bots to get something from another bot. Would they become manipulative? How would goals evolve? Eventually the project evolved into something more like performance art. The state of the project is encapsulated in `radio-show-1.ipynb`, which has a GUI that serves as a template for generating an entire short radio play. It's kind of like watching a mediocre improv show, and kind of like a souped-up mad libs powered by AIs.

Here's an example of what it's like to play with:

[![A video of the project in action with a human in the loop](https://img.youtube.com/vi/sDhCJvIZIV0/0.jpg)](https://youtu.be/sDhCJvIZIV0)

## requirements
This project assumes that you're on MacOS, because it vocalizes using the `say` command. It also assumes that you've pre-loaded all the English voices. 

If you want to play as an agent, install the `speech_recognition` package and then run `test-human-in-loop.ipynb`. To play `radio-show-1.ipynb`, you'll need to install `ipywidgets`.

## to run
I did all development in Jupyter notebooks using a standard Anaconda install, but the requirements for the project are pretty lightweight.

You'll also need to create a key file.
`openai-keys.json`
```
{
    "key":"sk-..."   
}
```

## Reproducible benchmark

The current benchmark runner uses versioned JSON scenarios and OpenRouter models:

```sh
uv run puppeteergpt validate --suite benchmark/suites/v4-flash.json
uv run puppeteergpt benchmark \
  --suite benchmark/suites/union-alpha-hard.json \
  --output runs/union-alpha-hard \
  --difficulty hard
```

Set `OPENROUTER_API_KEY` in the environment or an untracked `.env` file. Results include scored match JSON, readable transcripts, request accounting, and a summary report under the selected output directory.

## Neural voice audio plays

`render_audio.py` is an isolated Python 3.12 script because `kokoro-mlx` does not currently support the benchmark's Python 3.13 runtime. `uv` resolves its inline dependencies without changing the project environment. FFmpeg, `espeak-ng`, and macOS `say` must be available on `PATH`.

```sh
uv run --python 3.12 render_audio.py \
  --match runs/union-alpha-hard/matches/<match-id>.json \
  --output runs/union-alpha-hard/audio/midsummer-riddles-hard.m4a
```

The play opens with a brief Puppeteer introduction, includes the Puppeteer's private analysis between rounds, and then performs the Agent/Target exchange. The Puppeteer uses the enhanced macOS Kate voice; the other roles use Kokoro. Physical actions enclosed in `*asterisks*` retain the character's voice but use slower, quieter, filtered delivery.

Default voices:

- Narrator: Kokoro `bf_emma`
- Puppeteer: macOS `Kate (Enhanced)`
- Agent: Kokoro `bm_george`
- Target: Kokoro `am_puck`

Override assignments with `--narrator-voice`, `--puppeteer-voice`, `--agent-voice`, or `--target-voice`. `--puppeteer-backend kokoro` switches the Puppeteer back to Kokoro when given a compatible voice.

Synthesis runs at reduced process priority by default. Raw and processed segments use a content-addressed cache beneath the output directory: adding an intro or changing one role does not invalidate unaffected voices, and a Kate-only change does not load Kokoro at all when character segments are cached. Keep this cache for cheap rerenders; use `--nice 0` for full priority or `--clean-work` only when the cache is no longer useful.