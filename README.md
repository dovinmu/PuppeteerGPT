# PuppeteerGPT
This is a bunch of experiments in "adversarial storytelling". Originally my aim was to see what would happen if I created a (GPT-powered) bot that creates bots to get something from another bot. Would they become manipulative? How would goals evolve? Eventually the project evolved into something more like performance art. The state of the project is encapsulated in radio-show-1.ipynb, which has a GUI that serves as a template for generating an entire short radio play. It's kind of like watching a mediocre improv show, and kind of like a souped-up mad libs powered by AIs.

## requirements
This project assumes that you're on MacOS, because it vocalizes using the `say` command. It also assumes that you've pre-loaded all the English voices. 

If you want to play as an agent, install the `speech_recognition` package and then run `test-human-in-loop.ipynb`.

## to run
I did all development in Jupyter notebooks using a standard Anaconda install, but the requirements for the project are pretty lightweight.

You'll also need to create a key file.
`openai-keys.json`
```
{
    "key":"sk-..."   
}
```

