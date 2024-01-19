"""
A Python script to read the Gemini Antena feed (or any Atom XML feed)
and pack the authorized URLs into an ePub file

Based on following sources:
https://pypi.org/project/atoma/
https://github.com/aerkalov/ebooklib
https://tildegit.org/solderpunk/gemini-demo-1
"""

# Python Built-in
from decimal import DivisionByZero

# import re
from datetime import datetime

# Reading Gemini
import ssl
import socket
import urllib.parse
from email.message import Message

# ePub
#from ebooklib import epub

BASE_URL = "gemini://text.eapl.mx/posts"
TEXT_FOR_NEXT_PAGE = "Older posts"


def absolutise_url(base, relative):
    """Absolutise relative links."""

    # Based on https://tildegit.org/solderpunk/gemini-demo-1
    if "://" not in relative:
        if "gemini://" in base:
            # Python's URL tools somehow only work with known schemes?
            base = base.replace("gemini://", "http://")
            relative = urllib.parse.urljoin(base, relative)
            relative = relative.replace("http://", "gemini://")
        if "http://" in base:
            relative = urllib.parse.urljoin(base, relative)

    return relative


def read_url(url):
    """Gets an URL"""
    parsed_url = urllib.parse.urlparse(url)

    try:  # Get the Gemini content
        while True:
            s = socket.create_connection((parsed_url.netloc, 1965))
            context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            s = context.wrap_socket(s, server_hostname=parsed_url.netloc)
            s.sendall((url + "\r\n").encode("UTF-8"))

            # Get header and check for redirects
            fp = s.makefile("rb")
            header = fp.readline()
            header = header.decode("UTF-8").strip()
            split_header = header.split()
            status = split_header[0]
            mime = split_header[1]
            # Fix case when you receive a header like '20 text/gemini; lang=en'

            if status.startswith("1"):  # Handle input requests
                query = input("INPUT" + mime + "> ")  # Prompt
                url += "?" + urllib.parse.quote(query)  # Bit lazy...
            elif status.startswith("3"):  # Follow redirects
                url = absolutise_url(url, mime)
                parsed_url = urllib.parse.urlparse(url)
            else:  # Otherwise, we're done.
                break
    except DivisionByZero as err:
        print(err)
        return None

    # Fail if transaction was not successful
    if not status.startswith("2"):
        print(f"Error {status}: {mime}")
        return None

    if mime.startswith("text/"):
        # Decode according to declared charset
        m = Message()
        m["content-type"] = mime
        m.get_params()

        body = fp.read()
        body = body.decode(m.get_param("charset", "UTF-8"))

        return body

    return None

def is_valid_date(date_str, date_format="%Y-%m-%d") -> bool:
    """Returns True if the str is a valid YYYY-MM-DD."""
    try:
        datetime.strptime(date_str, date_format)
        return True
    except ValueError:
        return False


def extract_posts(body: str, posts: list) -> tuple[list, str | None]:
    """From a Gemtext, returns the URLs list, and URL for next page."""
    next_page: str = None

    for line in body.splitlines():
        # print(line)
        split_tuple = line.split(" ")

        if "Older posts" in line:
            next_page = split_tuple[1]

        # Not a link ? Skip to the next item
        if len(split_tuple) < 3:
            continue

        if is_valid_date(split_tuple[2]):
            url = absolutise_url(BASE_URL, split_tuple[1])
            time = split_tuple[2]
            title = " ".join(element for element in split_tuple[3:])
            posts.append((url, time, title))

    return posts, next_page


def get_post_list():
    """Checks the base URL, retrieves the found posts, iterates through each page
    and stops when there are no more pages."""
    current_url = BASE_URL
    are_more_posts = True
    posts_list = []

    while are_more_posts:
        print(f"{current_url=}")
        posts_list, next_page = extract_posts(read_url(current_url), posts_list)
        if next_page is not None:
            current_url = absolutise_url(BASE_URL, next_page)

        are_more_posts = next_page is not None

    # print(posts_list)
    return posts_list

def process_posts_list(posts: list):
    for post in posts:
        # 0 = URL, 1 = Date, 2 = Title
        body = read_url(post[0])
        if body is None:
            continue

        # Remove header
        # => /posts <  text.eapl.mx
        # Remove first 2 lines, and after
        lines = body.split('\n')
        body: str = '\n'.join(lines[2:])

        # Remove footer - After EOT
        parts = body.split("\n\nEOT", 1)
        body = parts[0]

        print(body)
        print('------')

# Main code starts here
if __name__ == "__main__":
    print("-------------------------------------")
    print("             Capsule to ePub         ")
    print("-------------------------------------")
    print(f"Reading capsule: {BASE_URL}")

    process_posts_list(get_post_list())
