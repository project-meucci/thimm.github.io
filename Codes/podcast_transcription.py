import pickle
from pathlib import Path
import unicodedata
import re
import feedparser
import pandas as pd
from pathlib import Path
import functools
import pathlib
import shutil
import requests
from tqdm.auto import tqdm
import requests
import pickle
from datetime import timedelta
import markdownify
import datetime

def prepare_segments(segments, window=7, stride=1):
    data = []
    for j in range(0, len(segments), stride):
        j_end = min(j+window, len(segments)-1)
        text = ''.join([x["text"] for x in segments[j:j_end]])
        start = segments[j]['start']
        end = segments[j_end]['end']
        row_id = f"{path.stem}-t{segments[j]['start']}"
        meta = {
                    "id": row_id,
                    "text": text.strip(),
                    "start": start,
                    "end": end
        }
        data.append(meta)
    return data


def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx:min(ndx + n, l)]
        
        
from functools import lru_cache

@lru_cache(100)
def load_meta(feedtitle, feedpath="feedmeta"):
    FEED_META = list(Path(feedpath).glob("*.pickle"))
    with open([x for x in FEED_META if x.stem.startswith(feedtitle)][0], "rb") as f:
        return pickle.load(f)
    
    
def filter_audio_link(link):
    if link["type"].startswith("audio"):
        return True
    
def get_episode_meta(feedtitle, episode_link):
    meta = load_meta(feedtitle)
    episode_meta = [
        x for x in meta["entries"] 
        if list(filter(filter_audio_link, x["links"]))[0]["href"].split("/")[-1].startswith(episode_link)
    ][0]
    episode_meta["feed_meta"] = meta["feed"]
    return episode_meta


def slugify(value, allow_unicode=True):
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    value = re.sub(r'[-\s]+', '-', value).strip('-_')
    return value.capitalize()


def download_episode(url, filename):
    if not filename.exists() and filename.stem not in [x.stem for x in Path("transcriptions").glob("**/*")]:
        r = requests.get(url, stream=True, allow_redirects=True)
        if r.status_code != 200:
            r.raise_for_status()  # Will only raise for 4xx codes, so...
            raise RuntimeError(f"Request to {url} returned status code {r.status_code}")
        file_size = int(r.headers.get('Content-Length', 0))

        path = pathlib.Path(filename).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        desc = "(Unknown total file size)" if file_size == 0 else ""
        r.raw.read = functools.partial(r.raw.read, decode_content=True)  # Decompress if needed
        with tqdm.wrapattr(r.raw, "read", total=file_size, desc=desc, leave=False) as r_raw:
            with path.open("wb") as f:
                shutil.copyfileobj(r_raw, f)
                
                
def create_markdown(transcriptions, podcast_meta, episode_meta, podlove_episode_path, podlove_config_path,  batch_size=5):
    
    try:
        href = [x for x in episode_meta["links"] if x["type"] == "text/html"][0]["href"]
        
    except IndexError:
        href = ""
        pass
    markdown = ""
    

    
    markdown += f"""---\ntitle: {" ".join([x.capitalize() for x in slugify(episode_meta["title"]).split("-")])}\ndescription: Transcripts for podcasts from the regenerative agriculture space. Search and find episodes and timestamps.\n---\n\n"""
  #   markdown += f"""<script src="https://cdn.podlove.org/web-player/embed.js"></script>
  #   <script>
  #       document.addEventListener('DOMContentLoaded', function () {{
  #         if (document.readyState === 'interactive' || document.readyState === 'complete') {{
  #           podlovePlayer('#player', 'https://raw.githubusercontent.com/Thimm/thimm.github.io/main/podlove/https://raw.githubusercontent.com/Thimm/thimm.github.io/main/podlove/{podlove_episode_path}', 'https://raw.githubusercontent.com/Thimm/thimm.github.io/main/podlove/{podlove_config_path}').then(registerExternalEvents('player'))
  #         }}
  #       }})
  # </script>\n\n"""
    markdown += f"""### {podcast_meta["feed"]["title"]}  ({pd.to_datetime(episode_meta["published"]).strftime("%Y-%m-%d")})  \n"""
    try:
        markdown += f"""### Author(s): {episode_meta["author"]}  \n"""
    except KeyError:
        pass
    for seq in batch(transcriptions["segments"], batch_size):
        start = seq[0]["start"]
        end = seq[-1]["end"]
        text = " ".join([x["text"] for x in seq])
        if href:
            href_with_time = f"{href}#t={timedelta(seconds=int(start))}"
            markdown += f"""
**[{timedelta(seconds=int(start))}-{timedelta(seconds=int(end))}]({href_with_time}):** {text}  """
        else:
             markdown += f"""
**{timedelta(seconds=int(start))}-{timedelta(seconds=int(end))}:** {text}  """
    return markdown


def get_podlove_transcripts(transcript, batch_size=3):
    podlove_transcripts = []
    for seq in batch(transcript["segments"], batch_size):
        start = seq[0]["start"]
        end = seq[-1]["end"]
        text = " ".join([x["text"] for x in seq])
        
        podlove_transcripts.append({
              "start": str(datetime.timedelta(seconds=start)),
              "start_ms": int(start*1000),
              "end": str(datetime.timedelta(seconds=end)),
              "end_ms": int(end*1000)+1,
              "text": text,
              "speaker": "1",
              "voice": " ",
            })
    return podlove_transcripts


def get_chapters(entry):
    chapters = requests.get(entry["podcast_chapters"]["url"]).json()["chapters"]
    for chapter in chapters:
        chapter["start"] = str(datetime.timedelta(seconds=chapter.pop("startTime")))

    return chapters

    
def get_audio(entry):
    audio = list(filter(lambda x: x if x["type"].startswith("audio") else False, entry["links"]))[0]
    
    return [
        {
          "url": audio["href"],
          "size": audio["length"],
          "title": "MP3 Audio (mp3)",
          "mimeType": audio["type"]
        }
    ]

def podlove_object(episode, feed_meta, transcript, batch_size=3):
    return {
        "version": 5,
        "show": {
        "title": feed_meta.get("title"),
        # "subtitle": "Der Podlove Entwickler:innen Podcast",
        "summary": feed_meta.get("summary"),
        "poster": feed_meta.get("image", {"href": "https://static.wixstatic.com/media/0c655a_b260b8cf3e1c4d30aaa970cdd38e742c~mv2.jpg/v1/fill/w_1277,h_753,al_c,q_85,enc_auto/0c655a_b260b8cf3e1c4d30aaa970cdd38e742c~mv2.jpg"}).get("href"),
        "link": feed_meta.get("link")
        },
        "title": episode.get("title"),
        "subtitle": episode.get("title"),
        "summary": episode.get("summary"),
        "publicationDate": episode.get("published"),
        "duration": episode.get("itunes_duration"),
        "poster": episode.get("image", {"href": "https://static.wixstatic.com/media/0c655a_b260b8cf3e1c4d30aaa970cdd38e742c~mv2.jpg/v1/fill/w_1277,h_753,al_c,q_85,enc_auto/0c655a_b260b8cf3e1c4d30aaa970cdd38e742c~mv2.jpg"}).get("href"),
        "link": episode.get("link"),

        "audio": get_audio(episode),

        "contributors": episode.get("authors"),
        # "transcripts": get_podlove_transcripts(transcript, batch_size),
    }


def get_podlove_config(feed_meta):
    return {
        "version": 5,
        "subscribe-button": {
        "feed": [x for x in feed_meta["links"] if "rss" in x["type"] or "atom" in x["type"]][0]["href"],
        "clients": [
          {
            "id": "apple-podcasts",
          },
          {
            "id": "antenna-pod"
          },
          {
            "id": "beyond-pod"
          },
          {
            "id": "castro"
          },
          {
            "id": "clementine"
          },
          {
            "id": "downcast"
          },
          {
            "id": "google-podcasts",
          },
          {
            "id": "gpodder"
          },
          {
            "id": "itunes"
          },
          {
            "id": "i-catcher"
          },
          {
            "id": "instacast"
          },
          {
            "id": "overcast"
          },
          {
            "id": "player-fm"
          },
          {
            "id": "pocket-casts"
          },
          {
            "id": "pocket-casts",
          },
          {
            "id": "pod-grasp"
          },
          {
            "id": "podcast-addict"
          },
          {
            "id": "podcast-republic"
          },
          {
            "id": "podcat"
          },
          {
            "id": "podscout"
          },
          {
            "id": "rss-radio"
          },
          {
            "id": "rss"
          }
        ]
        },

        "playlist": "playlist.json",

        "share": {
        "channels": [
          "facebook",
          "twitter",
          "whats-app",
          "linkedin",
          "pinterest",
          "xing",
          "mail",
          "link"
        ],
        "sharePlaytime": True
        },

        "features": {
        "persistTab": True,
        "persistPlaystate": True
        }
    }
