""" Spotify song sorter """
import base64
import json
import math
import sys
import logging
from urllib.parse import urlencode
from threading import Thread
import os
import requests
from requests_futures.sessions import FuturesSession
from flask import Flask, redirect, request, render_template, url_for
from under_proxy import get_flask_app

app = get_flask_app()


CLIENT_ID = os.environ.get("CLIENT_ID_SPOTIFY")
SECRET_KEY = os.environ.get("SECRET_KEY_SPOTIFY")
BASE_URL = "https://api.spotify.com/v1/"
URI = os.environ.get("N_SPOTIFY_URI")

# pylint: disable=R0903


class Song:
    """song datatype"""

    def __init__(self, name, artist, uri):
        self.name = name
        self.artist = artist
        self.lan = None
        self.uri = uri

    def __str__(self) -> str:
        return f"{self.name} by {self.artist}"


class Playlist:
    """playlist datatype"""

    def __init__(self, name, playlist_id, songs=None) -> None:
        self.name = name
        self.songs = songs if songs else []
        self.playlist_id = playlist_id

    def __str__(self) -> str:
        return f"{self.name} with id: {self.playlist_id}"


# pylint: enable=R0903


class SpotifyHandler:
    """makes api calls"""

    def __init__(self, client_id, secret_key):
        self.client_id = client_id
        self.secret_key = secret_key
        self.token = ""
        self.api_headers = {}
        self.logger = logging.getLogger("SpotifyHandlerLogger")
        self.logger.setLevel(logging.DEBUG)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def authorize(self, code):
        """authorizes app to connect to spotify account"""
        encoded_credentials = base64.b64encode(
            self.client_id.encode() + ":".encode() + self.secret_key.encode()
        ).decode()

        try:
            response = requests.post(
                url="https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": URI,
                },
                headers={"Authorization": "Basic " + encoded_credentials},
                timeout=10,
            )

            self.token = response.json()["access_token"]
        except Exception as e:
            self.logger.exception("Failed to obtain token. Message: " + str(e))
            return None

        self.api_headers = {"Authorization": "Bearer " + self.token}

        self.user_id = self.get_user_id()
        return self.token

    # pylint: disable=R0913
    def make_call(
        self, method, endpoint, headers=None, data=None, params=None
    ):
        """actual api calls"""
        if not headers:
            headers = self.api_headers

        try:
            response = getattr(requests, method)(
                BASE_URL + endpoint, headers=headers, params=params, data=data
            )
        except Exception as e:
            self.logger.exception(
                f"""
            Failed to execute an API request.
            Method: {method}
            Endpoint: {endpoint}
            Headers: {headers}
            Body: {data}
            Query Params: {params}

            Message: {str(e)}
            """
            )

        if response.status_code != 200:
            self.logger.info(
                f"""
            Failed to execute an API request.
            Method: {method}
            Endpoint: {endpoint}
            Headers: {headers}
            Body: {data}
            Query Params: {params}

            Message: {response.content}
            """
            )

        return response.json()

    # pylint: enable=R0913

    def get_resource(self, endpoint, headers=None, data=None, params=None):
        """gets items using pagination"""
        items = []

        total = self.make_call("get", endpoint, headers, data, params)["total"]

        for page in range(round(total / 50) or 1):
            try:
                items.extend(
                    self.make_call(
                        "get",
                        endpoint,
                        headers,
                        data,
                        params={"offset": page * 50, "limit": 50},
                    )["items"]
                )
            except Exception as e:
                self.logger.exception(
                    f"""
                Failed to execute an API pagination get_resource request.
                Endpoint: {endpoint}
                Headers: {headers}
                Body: {data}
                Query Params: {params}
                Page Number: {page}

                Message: {str(e)}
                """
                )

        return items

    def get_songs(self):
        """Creates song objects with its name, artist and uri."""
        return [
            Song(
                song["track"]["name"],
                song["track"]["artists"][0]["name"],
                song["track"]["uri"],
            )
            for song in self.get_resource("me/tracks")
        ]

    def get_user_id(self):
        """gets id for user"""
        return self.make_call("get", "me", headers=self.api_headers)["id"]

    def get_songs_and_lan(self):
        """gets songs and assigns them their language"""
        tracks = self.get_songs()
        with FuturesSession(max_workers=3) as session:
            for track in tracks:
                track.lan = session.get(
                    f"http://api.genius.com/search?q={track.name}%20{track.artist}",
                    headers={
                        "Authorization": "Bearer ticNcbIdYkprjA2F9QPw"
                        + "fr5sB0gc-dsfJveYzLxrYXwHksvCD05nvSnie1L4RMY6"
                    },
                )

        for track in tracks:
            try:
                track.lan = track.lan.result().json()["response"]["hits"][0][
                    "result"
                ]["language"]

                if track.lan is None:
                    track.lan = "unidentified"
            except (KeyError, IndexError):
                track.lan = "unidentified"

        return tracks

    def get_playlists(self):
        """creates playlist objects with name and id"""
        return [
            Playlist(playlist["name"], playlist["id"])
            for playlist in self.get_resource(
                f"users/{self.user_id}/playlists"
            )
        ]

    def empty_playlist(self, playlist_id):
        """empties chosen playlist"""

        for _ in range(
            math.ceil(
                (
                    self.make_call("get", f"playlists/{playlist_id}/tracks")[
                        "total"
                    ]
                    / 50
                )
            )
        ):
            self.make_call(
                "delete",
                f"playlists/{playlist_id}/tracks",
                data=json.dumps(
                    {
                        "tracks": [
                            {"uri": track["track"]["uri"]}
                            for track in self.make_call(
                                "get",
                                f"playlists/{playlist_id}/tracks",
                                params={"limit": 50},
                            )["items"]
                        ]
                    }
                ),
            )

    def update_playlist(self, playlist_id, songs):
        """Adds songs to the playlist"""
        for i in range(math.ceil(len(songs) / 90)):
            self.make_call(
                "post",
                f"playlists/{playlist_id}/tracks",
                data=json.dumps({"uris": songs[i * 90 : i * 90 + 90]}),
            )

    def create_playlist(self, name, songs):
        """Creates a playlist and adds songs to it"""
        playlist_id = self.make_call(
            "post",
            f"users/{self.user_id}/playlists",
            data=json.dumps({"name": name, "public": False}),
        ).get("id")

        if not playlist_id:
            self.logger.exception(
                f"Failed to create a playlist named {name}, skipping.."
            )
            return False

        for i in range(math.ceil(len(songs) / 90)):
            uris = {"uris": songs[i * 90 : (i + 1) * 90], "position": i * 90}
            if (
                self.make_call(
                    "post",
                    f"playlists/{playlist_id}/tracks",
                    headers=self.api_headers,
                    data=json.dumps(uris),
                ).status_code
                != 200
            ):
                self.logger.exception(
                    f"Failed to add songs to playlist {name}"
                )
                return False
        return True


@app.route("/")
def home():
    return render_template("home.html")


# Endpoint that redirects to spotify login page
@app.route("/start")
def start():
    return redirect(
        "https://accounts.spotify.com/authorize?"
        + urlencode(
            {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": URI,
                "scope": """user-library-read playlist-modify-private
                    playlist-read-private""",
            }
        )
    )


code = None


# Endpoint catching spotify's redirection and parses the code from the url
@app.route("/code")
def get_code():
    global code
    code = request.args.get("code")
    if not code:
        return "<h1>Failed to obtain code from Spotify API.</h1>"
    return redirect(url_for("main_func"))


# Starts background thread and shows goodbye page
@app.route("/main")
def main_func():
    Thread(target=process).start()

    return render_template("return.html")


def process():
    handler = SpotifyHandler(CLIENT_ID, SECRET_KEY)

    handler.logger.info("Process started")

    # If token not obtained, return
    if not handler.authorize(code):
        return False

    handler.logger.info("Authorized correctly")
    # Get all songs from user's favourites
    all_songs = handler.get_songs_and_lan()


    handler.logger.info("Collecting users's songs and playlists")
    # Create dict with language: [songs]
    lan_songs_dict = {lan: [] for lan in set(song.lan for song in all_songs)}
    for song in all_songs:
        lan_songs_dict[song.lan].append(song.uri)

    # Get all user's playlists
    playlists = handler.get_playlists()
    # Create dict playlist_name: playlist_id
    playlist_names = {
        playlist.name: playlist.playlist_id for playlist in playlists
    }

    handler.logger.info("Creating and populating playlists...")
    for lan in lan_songs_dict.keys():
        if lan in playlist_names.keys():
            # If playlist for that language exists, empty it
            handler.empty_playlist(playlist_names[lan])
            # Add songs to that empty playlist
            handler.update_playlist(playlist_names[lan], lan_songs_dict[lan])
        else:
            # Create a new playlist and add the songs
            handler.create_playlist(lan, lan_songs_dict[lan])

    handler.logger.info("Process finished")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5070)
