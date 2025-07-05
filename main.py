"""
Reads a Gemini capsule (tested on smol.pub) and creates a .epub file

Based on following sources:
https://github.com/aerkalov/ebooklib
https://tildegit.org/solderpunk/gemini-demo-1
"""

# Python Built-in
import re
import os
from datetime import datetime
import argparse
from typing import List

# Reading Gemini
import ssl
import socket
import urllib.parse
from email.message import Message

# ePub
from ebooklib import epub # type: ignore

parser = argparse.ArgumentParser(
                    description='Download gemlogs and save in epub for offline reading')
parser.add_argument('base_url', help='Url of the page that contains gemlog links')
parser.add_argument('-n', '--next-page', help='(regex) Text of a link that leads to the next page', default='Older posts')
parser.add_argument('-d', '--dir', help='Path to output directory', default='.')
parser.add_argument('-t', '--title', help='Title of the Epub')
parser.add_argument('-l', '--lang', help='Language of the Epub', default='en')
parser.add_argument('-a', '--author', help='Author of the Epub')
parser.add_argument('-f', '--filename', help='Filename of the Epub')

args = parser.parse_args()

BASE_URL = args.base_url
TEXT_FOR_NEXT_PAGE = args.next_page
OUTPUT_FOLDER = args.dir

domain = urllib.parse.urlparse(BASE_URL).netloc

EPUB_TITLE = args.title or f'{domain} Capsule'
EPUB_LANG = args.lang
EPUB_AUTHOR = args.author or domain
EPUB_FILENAME = args.filename or f"{domain.replace('.', '')}-capsule"


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


# Gemtext to HTML - Code block

# A dictionary that maps regex to match at the beginning of gmi lines
# to their corresponding HTML tag names. Used by convert_single_line().
tags_dict = {
    r"^# (.*)": "h1",
    r"^## (.*)": "h2",
    r"^### (.*)": "h3",
    r"^\* (.*)": "li",
    r"^> (.*)": "blockquote",
    r"^=>\s*(\S+)(\s+.*)?": "a",
}


def convert_single_line(gmi_line, url):
    """This function takes a string of gemtext as input and returns a string of HTML."""
    for pattern, _ in tags_dict.items():
        if match := re.match(pattern, gmi_line):
            tag = tags_dict[pattern]
            groups = match.groups()

            if tag == "a":
                href = groups[0]

                inner_text = str(groups[1]).strip() if len(groups) > 1 else href
                if inner_text == "None":
                    inner_text = href

                href = absolutise_url(base=url, relative=href)

                html_a = f"<p><a href='{href}'>{inner_text}</a></p>"
                return html_a

            inner_text = groups[0].strip()
            return f"<{tag}>{inner_text}</{tag}>"
    return f"<p>{gmi_line}</p>"


def gemtext_to_html(text, url) -> str:
    """Receives Gemtext and returns HTML."""
    preformat = False
    in_list = False

    html: str = ""

    for line in text.split("\n"):
        line = line.strip()

        if len(line):
            if line.startswith("```") or line.endswith("```"):
                preformat = not preformat
                repl = "<pre>" if preformat else "</pre>"
                html += re.sub(r"```", repl, line)
            elif preformat:
                html += line
            else:
                html_line = convert_single_line(line, url)
                if html_line.startswith("<li>"):
                    if not in_list:
                        in_list = True
                        html += "<ul>\n"

                    html += html_line
                elif in_list:
                    in_list = False
                    html += "</ul>\n"
                    html += html_line
                else:
                    html += html_line

        html += "\n"

    return html


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
    except socket.gaierror as ex:
        print(ex)
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


def extract_posts(body: str, url_list: list) -> tuple[list, str | None]:
    """From a Gemtext, returns the URLs list, and URL for next page."""
    next_page: str | None = None

    for line in body.splitlines():

        # Not a link ? Skip to the next item
        if line[0:2] != '=>':
            continue
        
        link_url_pos = 2
        while link_url_pos < len(line) and line[link_url_pos] in [' ', '\t']:
            link_url_pos += 1
        link_separator_pos = line.find(' ', link_url_pos)
        link_text_pos = link_separator_pos
        while link_text_pos < len(line) and line[link_text_pos] in [' ', '\t']:
            link_text_pos += 1

        # No link name, therefore no date, so we skip
        if link_separator_pos == -1 or link_separator_pos == len(line)-1:
            continue

        link_url = line[link_url_pos:link_separator_pos]
        link_text = line[link_text_pos:]
        link_name_pos = link_text.find(' ')
        if link_name_pos + 1 >= len(link_text):
            continue
        link_time = link_text[:link_name_pos]
        link_name = link_text[link_name_pos+1:]

        if TEXT_FOR_NEXT_PAGE == link_text:
            next_page = link_url

        if is_valid_date(link_time):
            url = absolutise_url(BASE_URL, link_url)
            url_list.append((url, link_time, link_name))

    return url_list, next_page


def get_url_list() -> list:
    """Checks the base URL, retrieves the found posts, iterates through each page
    and stops when there are no more pages."""
    current_url = BASE_URL
    are_more_posts = True
    url_list: list[str] = []

    while are_more_posts:
        print(f"Loading {current_url}")
        body: str | None = read_url(current_url)
        if body is None:
            print("A problem occured. Check your Internet or the URL!")
            return []

        url_list, next_page = extract_posts(body, url_list)
        if next_page is not None:
            current_url = absolutise_url(BASE_URL, next_page)

        are_more_posts = next_page is not None

    # print(url_list)
    return url_list


def process_url_list(url_list: list) -> list:
    """Receives a list of URLs, gets it, and returns a list of dict, with
    data for all the posts"""
    posts_content: list = []

    for post in url_list:
        # 0 = URL, 1 = Date, 2 = Title
        url: str = post[0]
        print(f"Loading {url}")
        body: str = read_url(url)
        if body is None:
            continue

        # Remove header
        # => /posts <  text.eapl.mx
        # Remove first 2 lines, and after
        lines = body.split("\n")
        body = "\n".join(lines[2:])

        # Remove footer - After EOT
        parts = body.split("\n\nEOT", 1)
        body = parts[0]

        html = gemtext_to_html(body, url)
        html += f"\n<hr><p><a href={url}>{url}</a></p>"

        post = {
            "url": url,
            "date": post[1],
            "title": post[2],
            "html": html,
        }

        posts_content.append(post)

        # print(body)
        # print('------')

    return posts_content


def create_epub(posts_list: list):
    """Receives an list of dictionaries, and puts them into an epub."""
    book = epub.EpubBook()  # Start the ePub library

    # Set metadata
    book.set_identifier(EPUB_TITLE)
    current_date: str = datetime.now().strftime("%Y-%m-%d")
    title = f"{EPUB_TITLE}\n({current_date})"
    print(f"Title for the ePub: {title}")

    book.set_title(title)
    book.set_language(EPUB_LANG)
    book.add_author(EPUB_AUTHOR)

    chapters: list = []  # Empty list to store every URL into a ePub Chapter

    for post in posts_list:
        chapter = epub.EpubHtml(
            title=f"{post['date']} {post['title']}",
            file_name=f'chapter_{str(len(chapters)).rjust(3, "0")}.xhtml',
            lang="en",
        )
        chapter.content = post["html"]
        book.add_item(chapter)

        chapters.append(chapter)

    # Define Table Of Contents
    book.toc = chapters

    # Add default NCX and Nav file
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Basic spine
    book.spine = ["nav"] + chapters

    # Write the file
    file_name: str = f"{EPUB_FILENAME}-{current_date}.epub"
    file_path: str = os.path.join(OUTPUT_FOLDER, file_name)
    result = epub.write_epub(file_path, book, {})
    if result == False:
        print(f"An error occured while tryin to write to {file_path}")
    else:
        print(f"ePub created to {file_path}")


# Main code starts here
if __name__ == "__main__":
    print("-----------------------------------------")
    print("             Capsule to ePub             ")
    print("-----------------------------------------")

    posts: list = process_url_list(get_url_list())
    create_epub(posts)
