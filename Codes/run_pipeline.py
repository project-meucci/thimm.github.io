import pip

def install(package):
    pip.main(['install', package])
try:
    import feedparser
except ModuleNotFoundError:
    install('feedparser') 
try:
    import whisper
except ModuleNotFoundError:
    install('git+https://github.com/openai/whisper.git') 
try:
    import markdownify
except ModuleNotFoundError:
    install('markdownify') 

import pandas as pd
from pathlib import Path
import functools
import pathlib
import shutil
import requests
from tqdm.auto import tqdm
import requests
import pickle
import json
import torch
import subprocess
from requests import HTTPError
from requests.exceptions import MissingSchema
from podcast_transcription import create_markdown, download_episode, slugify, podlove_object, get_podlove_config
import pickle
from feeds import feeds

DOWNLOAD_FOLDER = Path("data")
FEEDMETA = Path("feedmeta")
MARKDOWN = Path("markdown")
TRRANSCRIPTIONS = Path("transcriptions")
PODLOVE = Path("podlove")
PODLOVE.mkdir(exist_ok=True)
FEEDMETA.mkdir(exist_ok=True)

device = "cuda" if torch.cuda.is_available() else "cpu"
print(device)
model = whisper.load_model("medium.en").to(device)


for feed in tqdm(feeds, desc="Podcast"):
    podcast = feedparser.parse(feed)
    podcast_title = podcast["feed"]["title"]
    
    
    with open(FEEDMETA / f"{podcast_title}.meta.pickle", "wb") as f:
        pickle.dump(podcast, f)
    
    for episode in tqdm(podcast["entries"], desc=f"Podcast {podcast_title[:30]}"):
      
        episode_title = slugify(episode["title"])
        markdown_path = MARKDOWN / podcast_title 
        markdown_path.mkdir(exist_ok=True)
        markdown_path = markdown_path / f"{episode_title}.md"

        if not markdown_path.exists():
            episode_file_path = DOWNLOAD_FOLDER / f"{episode_title}.mp3"
            try:
                download_episode(
                    url=[x for x in episode["links"] if x["type"].startswith("audio")][0]["href"],
                    filename=episode_file_path
                )
            except (HTTPError, MissingSchema) as e:
                print(episode["title"], e)
                continue


            transcriptions_path = TRRANSCRIPTIONS / podcast_title 
            transcriptions_path.mkdir(exist_ok=True)
            transcriptions_episode_path = transcriptions_path / f"{episode_title}.pickle"
            if not transcriptions_episode_path.exists():
                transcriptions = model.transcribe(str(episode_file_path))
                with open(transcriptions_episode_path, "wb") as f:
                    pickle.dump(transcriptions, f)
            else:
                with open(transcriptions_episode_path, "rb") as f:
                    transcriptions = pickle.load(f)

            with open(markdown_path, "w") as f:
                markdown = create_markdown(transcriptions, podcast, episode)
                f.write(markdown)

            episode_file_path.unlink()
            
subprocess.run(["chmod", "400", "/home/jovyan/.ssh/id_ed25519"])         
subprocess.run(["cp -r markdown/* ../docs/"], shell=True)         
subprocess.run(["git", "pull"])
subprocess.run(["git", "add", "../docs"])
subprocess.run(["git", "commit", "-m", '"New content"'])
subprocess.run(["git", "push"])


