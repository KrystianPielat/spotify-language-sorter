  This application takes all the liked songs of a user and classifies them by language creating a playlist for each of them, and it is written in Python using Flask.

  To begin, the user has to authorize the app to access their Spotify account data through the Spotify API. Then the app gets all the songs from user's favourites, and using their titles it attemps to determine their language through the Genius API. After assigning a language to each song, it creates playlists with songs in each language. If a playlist for a given language already exists, it will be updated.

  Regarding authorization, the first step is to ask the user to log in their Spotify account so that the app can access their information, after this the user is redirected back to the app with a code. This code is then used to make a POST request the /api/token endpoint, from this we get the access token which allows us to actually make use of the user's information.

An issue encountered was that for getting the languages of the songs, the program uses the Genius API to send requests attempting to match each song with its language. This is a very time consuming task, which is why I implemented concurrent programming to be able to send parallel requests which reduces significantly the execution time.

Finally, in regards to hosting, it is done using Docker to create a container which is an isolated lightweight Linux environment with all necessary dependencies installed.
