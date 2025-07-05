# gemfeed-to-epub

Starts from an URL, gets all links in Gemfeed format, get all the texts.
Packs everything into an epub.

## How to run

1. Create and activate venv (command may be different on other OS)
```
python3 -m venv venv
source venv/bin/activate
```
2. Install dependencies
```
pip install -r requirements.txt
```
3. Run the script
```
python3 main.py <URL>
```
4. To see available flags, use the 'help' flag
```
python3 main.py -h
```
