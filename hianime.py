import requests, re, json, subprocess, time, html, os
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from Crypto.Cipher import AES
import base64
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

# --- Argparse ---
parser = argparse.ArgumentParser()
parser.add_argument("--command", action="store_true", help="Print the final mpv command and exit")
args = parser.parse_args()

# --- Configuration & Caching (Global Scope) ---
BASE_URL = "https://hianime.to"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
REQUEST_TIMEOUT = 15
SESSION = requests.Session(); SESSION.headers.update(HEADERS)
HISTORY_FILE = os.path.join(BASE_DIR, "history.json"); HISTORY_LIMIT = 10; PINS_FILE = os.path.join(BASE_DIR, "pins.json")
CACHE = {'episodes': {}, 'servers': {}, 'keys': None, 'titles': {}}
SUBTITLE_BASE_DIR = "F:/Subtitle" # Your specified directory
JIMAKU_API_KEY = os.getenv("JIMAKU_API_KEY")
JIMAKU_HEADERS = {"Authorization": JIMAKU_API_KEY}
JIMAKU_BASE_URL = "https://jimaku.cc"
SCRIPT_DIR = Path(__file__).resolve().parent
TEMP_DIR = SCRIPT_DIR / "temp_subs"
TEMP_DIR.mkdir(exist_ok=True)
CLEANUP_SPAN = 24 * 60 * 60

# --- Opening config.json ---
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

# --- History function and Pin Function ---
def load_file(filepath):
    if not os.path.exists(filepath): return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, IOError): return []
def save_file(data, filepath):
    try:
        with open(filepath, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)
    except IOError: print(f"Warning: Could not save {filepath}.")
def update_history(history, metadata, series_url):
    history = [item for item in history if item['url'] != series_url]
    history.insert(0, {'url': series_url, 'english_title': metadata['english_title'], 'japanese_title': metadata['japanese_title']})
    return history[:HISTORY_LIMIT]
def add_pin(pins, item_to_pin):
    if any(p['url'] == item_to_pin['url'] for p in pins):
        print("--> This series is already pinned."); return pins
    pins.insert(0, item_to_pin); save_file(pins, PINS_FILE)
    display_title = item_to_pin.get('japanese_title') or item_to_pin.get('english_title')
    print(f"--> Pinned '{display_title}'."); return pins
def manage_pins(pins):
    if not pins: print("\nYou have no pinned series to manage."); time.sleep(2); return pins
    while True:
        print("\n--- Manage Pinned Series ---")
        for i, item in enumerate(pins, 1):
            display_title = item.get('japanese_title') or item.get('english_title') or "Unknown Title"
            print(f"  [{i}] {display_title}")
        print("\nEnter a number to unpin, or 'q' to return to the main menu.")
        choice_str = input("Your choice: ")
        if choice_str.lower() in ['q', 'quit', 'back']: return pins
        try:
            choice = int(choice_str)
            if 1 <= choice <= len(pins):
                removed = pins.pop(choice - 1); save_file(pins, PINS_FILE)
                print(f"--> Unpinned '{removed.get('japanese_title') or removed.get('english_title')}'.")
            else: print("Invalid number.")
        except ValueError: print("Invalid input.")
        
# --- Helper Functions ---
def get_keys_from_repo():
    if CACHE['keys']: return CACHE['keys']
    try:
        repo_url = "https://raw.githubusercontent.com/yogesh-hacker/MegacloudKeys/refs/heads/main/keys.json"
        keys = SESSION.get(repo_url, timeout=REQUEST_TIMEOUT).json()
        CACHE['keys'] = keys['mega'], keys.get('vidplay'); print("    -> Keys cached for this session.")
        return CACHE['keys']
    except Exception: return "80830978219438573984724834823458", "80830978219438573984724834823458"

def decrypt_data(key, encrypted_str):
    decoded_str = base64.b64decode(encrypted_str); salt = decoded_str[:16]; ciphertext = decoded_str[16:]
    key_and_iv = b''; temp_key = b''
    while len(key_and_iv) < 48:
        temp_key = hashlib.md5(temp_key + key.encode() + salt).digest(); key_and_iv += temp_key
    aes_key = key_and_iv[:32]; aes_iv = key_and_iv[32:48]
    cipher = AES.new(aes_key, AES.MODE_CBC, iv=aes_iv); decrypted_bytes = cipher.decrypt(ciphertext)
    padding_len = decrypted_bytes[-1]; return decrypted_bytes[:-padding_len]

def extract_megacloud(iframe_url):
    try:
        # Use a standard PC User-Agent (Matches the logs better than Android)
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        
        parsed_url = urlparse(iframe_url)
        # DYNAMIC REFERER: This captures 'megacloud.blog' or 'megacloud.tv' automatically
        domain = parsed_url.netloc 
        custom_referer = f"{parsed_url.scheme}://{domain}/"

        extractor_headers = {
            "Accept": "*/*", 
            "X-Requested-With": "XMLHttpRequest", 
            "Referer": custom_referer, 
            "User-Agent": user_agent,
            "Origin": custom_referer[:-1] # Remove trailing slash for Origin
        }
        
        print(f"--> [Extractor] Fetching embed from: {custom_referer}")
        response = SESSION.get(iframe_url, headers=extractor_headers, timeout=REQUEST_TIMEOUT)
        response_text = response.text
        
        soup = BeautifulSoup(response_text, 'html.parser')
        video_tag = soup.select_one('#megacloud-player')
        
        if not video_tag: raise ValueError("Could not find '#megacloud-player' tag.")
            
        file_id = video_tag['data-id']
        match = re.search(r'\b[a-zA-Z0-9]{48}\b', response_text)
        if not match: raise ValueError("Could not find nonce in HTML.")
        nonce = match.group()
        
        mega_key, vid_key = get_keys_from_repo()
        
        sources_url = f'{custom_referer}embed-2/v3/e-1/getSources?id={file_id}&_k={nonce}'
        
        # API Headers must match the Embed Headers
        api_headers = extractor_headers.copy()
        api_headers["Accept"] = "application/json"
        
        response_json = SESSION.get(sources_url, headers=api_headers, timeout=REQUEST_TIMEOUT).json()
        
        encrypted_str = response_json.get('sources')
        tracks = response_json.get('tracks', [])
        
        if isinstance(encrypted_str, str) and encrypted_str:
            try: 
                decrypted_json_str = decrypt_data(mega_key, encrypted_str).decode()
            except: 
                decrypted_json_str = decrypt_data(vid_key, encrypted_str).decode()
                
            sources = json.loads(decrypted_json_str)
            video_url = sources[0]['file']
            
            return {
                "url": video_url, 
                "user_agent": user_agent, 
                "referer": custom_referer, # PASS THE DYNAMIC REFERER
                "tracks": tracks
            }
        elif isinstance(encrypted_str, list) and encrypted_str:
             return {
                 "url": encrypted_str[0].get('file'), 
                 "user_agent": user_agent, 
                 "referer": custom_referer, 
                 "tracks": tracks
             }
        else: 
            raise ValueError("Server did not return a valid 'sources' payload.")
            
    except Exception as e: 
        print(f"--> [Extractor Error] {e}")
        return None

def get_series_metadata(series_url, history):
    if series_url in CACHE['titles']: return CACHE['titles'][series_url], history
    print(f"--> Fetching series metadata from: {series_url}");
    try:
        response = SESSION.get(series_url, timeout=REQUEST_TIMEOUT); soup = BeautifulSoup(response.text, 'html.parser')
        target_link = soup.select_one("h2.film-name a.dynamic-name")
        if target_link: english = html.unescape(target_link.text.strip()); japanese = html.unescape(target_link.get('data-jname', '')) if target_link.has_attr('data-jname') else None
        else:
            target_breadcrumb = soup.select_one("li.breadcrumb-item.active.dynamic-name")
            if not target_breadcrumb: raise ValueError("Could not find title using any known pattern.")
            english = html.unescape(target_breadcrumb.text.strip()).replace("Watching ", ""); japanese = html.unescape(target_breadcrumb.get('data-jname', '')) if target_breadcrumb.has_attr('data-jname') else None
        metadata = {'english_title': english, 'japanese_title': japanese}; CACHE['titles'][series_url] = metadata
        new_history = update_history(history, metadata, series_url); save_file(new_history, HISTORY_FILE)
        return metadata, new_history
    except Exception as e: print(f"An error occurred in fetching series: {e}"); return None, history
def get_all_episodes(series_url):
    if series_url in CACHE['episodes']: return CACHE['episodes'][series_url]
    try:
        print(f"--> Fetching full episode data via API..."); response = SESSION.get(series_url, timeout=REQUEST_TIMEOUT); soup = BeautifulSoup(response.text, 'html.parser')
        sync_data_script = soup.find('script', {'id': 'syncData'}); anime_id = json.loads(sync_data_script.string).get('anime_id')
        api_url = f"{BASE_URL}/ajax/v2/episode/list/{anime_id}"; response = SESSION.get(api_url, headers={'Referer': series_url}, timeout=REQUEST_TIMEOUT)
        episodes_html = response.json().get('html', ''); soup = BeautifulSoup(episodes_html, 'lxml')
        episodes = [{'num': i + 1, 'english_title': html.unescape(link.get('title', 'No Title')), 'japanese_title': html.unescape(ep_name_div['data-jname']) if (ep_name_div := link.select_one('.ep-name.e-dynamic-name')) and ep_name_div.has_attr('data-jname') else None, 'url': BASE_URL + link['href'], 'id': link['data-id']} for i, link in enumerate(soup.find_all('a', class_='ssl-item'))]
        print(f"--> Found and cached {len(episodes)} episodes."); CACHE['episodes'][series_url] = episodes; return episodes
    except Exception as e: print(f" Fetching episode extractor failed: {e}"); return []
def get_episode_servers(episode_id):
    if episode_id in CACHE['servers']: return CACHE['servers'][episode_id]
    try:
        servers_url = f"{BASE_URL}/ajax/v2/episode/servers?episodeId={episode_id}"; r = SESSION.get(servers_url, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(r.json().get("html", ""), "html.parser"); servers = []
        server_counts = {}
        for div in soup.select("div.server-item"):
            server_name = div.text.strip(); server_counts[server_name] = server_counts.get(server_name, 0) + 1
            final_name = server_name + " (Dub)" if server_counts[server_name] > 1 else server_name
            servers.append({"id": div.get("data-id"), "name": final_name})
        CACHE['servers'][episode_id] = servers; return servers
    except Exception: return []

# --- Testing the server if the server is not offline ---
def launch_and_monitor_mpv(mpv_command_list):
    if not config.get("enable_viability_check", True):
        print("\n--- LAUNCHING VIDEO ---")
        print("--> Viability check disabled. Handing over control to player.")
        try:
            # No stdout capture = mpv owns the terminal and nothing kills it after 20s
            subprocess.call(mpv_command_list)
            return True
        except Exception as e:
            print(f"--> Failed to launch mpv: {e}")
            return False

    print("\n--- LAUNCHING VIDEO ---"); print("--> Monitoring stream viability (20 second timeout)...")
    try:
        with subprocess.Popen(mpv_command_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace') as process:
            start_time = time.time()
            for line in iter(process.stdout.readline, ''):
                if "(+) Video --vid=1" in line:
                    print("--> Stream is valid. Handing over control to player."); process.stdout.close(); process.wait(); return True
                if "Opening failed" in line or "HTTP error" in line:
                    print("--> ❕ Dead stream detected by MPV. Terminating."); process.terminate(); return False
                if time.time() - start_time > 20:
                    print("--> ❕ Timed out. Terminating hung process."); process.terminate(); return False
            print("--> ❕ MPV exited prematurely."); return False
    except Exception as e: print(f"--> An unexpected error occurred in the watchdog: {e}"); return False

# --- JIMAKU MODULE/API ---
def search_jimaku(query):
    print(f"\n--> [Jimaku] Searching for '{query}'...")
    if not JIMAKU_API_KEY: print("--> JIMAKU_API_KEY not set. Skipping search."); return None
    try:
        response = SESSION.get(f"{JIMAKU_BASE_URL}/api/entries/search", headers=JIMAKU_HEADERS, params={"query": query, "anime": "true"}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e: print(f"--> [Jimaku] Search failed: {e}"); return None
def get_jimaku_files(entry_id):
    print(f"--> [Jimaku] Fetching file list for entry ID: {entry_id}")
    if not JIMAKU_API_KEY: return []
    try:
        response = SESSION.get(f"{JIMAKU_BASE_URL}/api/entries/{entry_id}/files", headers=JIMAKU_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception: return []
def extract_episode_num(filename):
    patterns = [
        # 1. Look for explicit hash syntax (e.g., "Show #13") - Priorities this!
        re.compile(r"#(\d{1,3})"), 
        
        # 2. Look for explicit Episode notation (EP01, E01)
        re.compile(r"EP?(\d{1,3})", re.I), 
        
        # 3. Look for " - 01 " format (Specific to AnimeKaizoku/HorribleSubs style)
        # We enforce spaces around the hyphen to avoid matching dates like 2013-02-14
        re.compile(r"\s-\s(\d{1,3})(?:v\d)?(?:\s|\[|\.)"), 
        
        # 4. Look for [01] at the start or inside brackets
        re.compile(r"\[(\d{1,3})\]"),
        
        # 5. Last resort: The generic spacer pattern (Moved to bottom)
        # Note: This is risky because of dates, but kept as a fallback.
        re.compile(r"[._\s](\d{1,3})[._\s]") 
    ]
    
    for pat in patterns:
        m = pat.search(filename)
        if m: 
            return int(m.group(1))
            
    return 0
def download_jimaku_sub(file_data, series_title):
    url = file_data['url']
    filename = file_data['name']
    
    series_folder_name = re.sub(r'[\\/:*?"<>|]', "_", series_title)
    series_dir = os.path.join(SUBTITLE_BASE_DIR, series_folder_name)
    os.makedirs(series_dir, exist_ok=True)
    filepath = os.path.join(series_dir, filename)
    
    if os.path.exists(filepath):
        print(f"--> [Jimaku] Already exists: '{filename}'")
        return filepath

    print(f"--> [Jimaku] Downloading '{filename}'...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=30); response.raise_for_status()
        with open(filepath, 'wb') as f: f.write(response.content)
        print(f"--> [Jimaku] Success! Saved to '{filepath}'.")
        return filepath
    except Exception as e: print(f"--> [Jimaku] Download failed: {e}"); return None
    
# --- Downloading subs english.vtt from megacloud and Converting to srt as a temp ---
def download_and_convert_sub(url, index, name="sub"):
    today = datetime.today()
    vtt_path = TEMP_DIR / f"{name}_{today.year}-{today.month}-{today.day}_{today.hour}-{today.minute}-{today.second}({index}).vtt"
    srt_path = TEMP_DIR / f"{name}_{today.year}-{today.month}-{today.day}_{today.hour}-{today.minute}-{today.second}({index}).srt"

    # download subtitle
    try:
        print(f"\n--> [FFmpeg] Downloading english subs '{url}' to convert...")
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(vtt_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
    except Exception as e:
        print(f"--> [FFmpeg] Downloading failed as exception ({e})")
        
    # convert to srt with ffmpeg
    try:
        if Path(vtt_path).is_file():
            print(f"--> [FFmpeg] Converting the english.vtt to .srt as a temp...")
            subprocess.run([
                "ffmpeg", "-loglevel", "error", "-i", str(vtt_path), str(srt_path)
            ], check=True)
            print(f"--> [FFmpeg] Succesfully converted to {srt_path}")
            return srt_path
        else:
            print(f"--> [FFmpeg] Skipping the convert. No subs to be found.")
            return None
    except FileNotFoundError:
        print("--> [FFmpeg] Skipping convert. 'ffmpeg' not found on system.")
        return None 
    except subprocess.CalledProcessError as e:
        print(f"--> [FFmpeg] Converting failed (ffmpeg error: {e})")
        if srt_path.exists():
            srt_path.unlink()
        return None
    except Exception as e:
        print(f"--> [FFmpeg] Unexpected exception occurred: {e}")
        return None
        
# --- Deleating subs files in temp folder ---
def cleanup_old_subs():
    now = time.time()
    for f in TEMP_DIR.glob("*.srt"):
        if now - f.stat().st_mtime > CLEANUP_SPAN:
            f.unlink()
    for f in TEMP_DIR.glob("*.vtt"):
        if now - f.stat().st_mtime > CLEANUP_SPAN:
            f.unlink()
            
# --- Main Application ---
def main():
    if not JIMAKU_API_KEY:
        print("--> [WARNING]: JIMAKU_API_KEY environment variable not set. Jimaku search will be unavailable.")
    pins = load_file(PINS_FILE); history = load_file(HISTORY_FILE)
    cleanup_old_subs()
    while True:
        # Making list recent history and pinned series
        print("\n" + "#"*20 + " MAIN MENU " + "#"*20)
        bookmarks = []
        if pins:
            print("--- Pinned Series ---");
            for i, item in enumerate(pins, 1):
                display_title = item.get('japanese_title') or item.get('english_title') or "Unknown Title"
                print(f"  [{i}] {display_title}"); bookmarks.append(item)
            print("-" * 20)
        unpinned_history = [item for item in history if not any(p['url'] == item['url'] for p in pins)]
        if unpinned_history:
            print("--- Recent History ---")
            
            seen = set()
            for i, item in enumerate(unpinned_history, 1):
                display_title = item.get('japanese_title') or item.get('english_title') or "Unknown Title"

                if display_title in seen:
                    continue
                seen.add(display_title)
                
                print(f"  [{len(pins) + i}] {display_title}"); bookmarks.append(item)
            print("-" * 20)
        print("Paste a URL, enter a number to select, 'pin [num]' to pin, 'manage' to unpin, or 'q' to quit.")
        url_input = input("Your command: ").strip()
        
        if url_input.lower() in ['q', 'quit', 'exit']: print("Goodbye!"); break
        if url_input.lower() == 'manage': pins = manage_pins(pins); continue
        
        if url_input.lower().startswith('pin '):
            try:
                num_to_pin = int(url_input.split(' ')[1])
                if 1 <= num_to_pin <= len(bookmarks):
                    pins = add_pin(pins, bookmarks[num_to_pin - 1])
                else: print("Invalid number to pin.")
            except (ValueError, IndexError): print("Invalid pin command. Use 'pin [number]'.")
            continue
        
        series_url = None
        if url_input.isdigit():
            try:
                choice = int(url_input)
                if 1 <= choice <= len(bookmarks): series_url = bookmarks[choice - 1]['url']
                else: print("Invalid number."); continue
            except (ValueError, IndexError): print("Invalid selection."); continue
        else:
            series_url = url_input
        
        metadata, history = get_series_metadata(series_url, history)
        if not metadata: print("\nCould not retrieve series metadata."); continue
        
        episodes = get_all_episodes(series_url)
        if not episodes: print("\nCould not retrieve episode list."); continue

        # Main cli logic
        while True:
            print("\n" + "="*50); series_display_title = metadata['japanese_title'] or metadata['english_title']; print(f"--- Series: {series_display_title} ---")
            for ep in episodes: ep_display_title = ep['japanese_title'] or ep['english_title']; print(f"  [{ep['num']}] {ep_display_title}")
            print("\nTo select a new series, type 'n'. To pin this series, type 'p'. To exit, type 'q'.")
            choice_str = input("\nEnter the episode number you want to watch: ")
            
            if choice_str.lower() in ['q', 'quit', 'exit']: print("Session ended. Goodbye!"); exit()
            if choice_str.lower() in ['n', 'new', 'back']: print("Returning to series selection..."); break
            if choice_str.lower() in ['p', 'pin']: pins = add_pin(pins, {'url': series_url, **metadata}); continue
            
            try: chosen_ep = next(ep for ep in episodes if ep['num'] == int(choice_str))
            except (ValueError, StopIteration): print("Invalid number selected."); continue
            
            servers = get_episode_servers(chosen_ep['id'])
            if not servers: print("\n❌ No servers found."); continue

            print("\n--- Available Servers ---")
            for i, server in enumerate(servers, 1):
                print(f"  [{i}] {server['name']}")
            
            server_choice_str = input("\nEnter server number (or press Enter for auto-select): ").strip()
            
            servers_to_try = []
            if not server_choice_str:
                print("--> Auto-select enabled. Trying all servers in order...")
                servers_to_try = servers
            else:
                try:
                    choice = int(server_choice_str)
                    if 1 <= choice <= len(servers):
                        servers_to_try = [servers[choice - 1]]
                    else:
                        print("Invalid server number. Returning to episode list.")
                        continue
                except ValueError:
                    print("Invalid input. Returning to episode list.")
                    continue
                    
            # Server logic
            stream_found = False
            for server in servers_to_try:
                print(f"\n--> Selecting server '{server['name']}'...")
                stream_data = None; max_retries = 3
                for attempt in range(max_retries):
                    print(f"--> Extractor Attempt {attempt + 1}/{max_retries}...")
                    api_url = f"{BASE_URL}/ajax/v2/episode/sources?id={server['id']}"
                    try:
                        data = requests.get(api_url, headers=HEADERS, timeout=REQUEST_TIMEOUT).json()
                        iframe_link = data.get("link")
                        if iframe_link and "megacloud" in iframe_link:
                            stream_data_candidate = extract_megacloud(iframe_link)
                            if stream_data_candidate:
                                stream_data = stream_data_candidate; break
                    except Exception: pass
                    if attempt < max_retries - 1: print("--> Extractor failed. Waiting 2 seconds..."); time.sleep(2)
                
                if stream_data:
                    stream_data['server_name'] = server['name']
                    ep_title = chosen_ep['japanese_title'] or chosen_ep['english_title']
                    display_title = (f"[Ep. {chosen_ep['num']}] {ep_title} ({stream_data['server_name']})")
                    
                    # 1. Prepare Cookies
                    # Convert requests.Session cookies to a string format "key=value; key2=value2"
                    cookies_dict = SESSION.cookies.get_dict()
                    cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
                    
                    # 2. Get the Dynamic Referer we extracted
                    ref = stream_data["referer"] # e.g., https://megacloud.blog/
                    
                    # 3. Construct Headers for MPV
                    # We add Sec-Fetch headers to mimic the browser logs you sent
                    header_fields = [
                        f"Referer: {ref}",
                        f"Origin: {ref.rstrip('/')}",
                        f"Cookie: {cookie_string}",
                        "Sec-Fetch-Dest: empty",
                        "Sec-Fetch-Mode: cors",
                        "Sec-Fetch-Site: cross-site"
                    ]
                    
                    mpv_command = [
                        'mpv', 
                        stream_data["url"], 
                        f'--user-agent={stream_data["user_agent"]}', 
                        '--ytdl-format=bestvideo+bestaudio/best', 
                        f'--title={display_title}', 
                        '--script-opts=osc-title=${title}',
                        '--tls-verify=no',
                        f'--http-header-fields={",".join(header_fields)}'
                    ]
                    
                    loaded_subs = []
                    
                    # Load Jimaku (Japanese) subs FIRST so they become the earlier tracks (default display)
                    has_jimaku = False
                    if JIMAKU_API_KEY and config.get("enable_jimaku", True):
                        print("\n--> [Jimaku] Enabled. Proceeding...")
                        search_query = metadata['japanese_title'] or metadata['english_title']
                        jimaku_results = search_jimaku(search_query)
                        
                        if not jimaku_results:
                            print("--> [Jimaku] No results found on Jimaku.cc for this series.")
                        else:
                            if len(jimaku_results) == 1:
                                chosen_jimaku_anime = jimaku_results[0]
                                print(f"--> [Jimaku] One result found: {chosen_jimaku_anime['name']}")
                            elif any(r['name'] == series_display_title for r in jimaku_results):
                                # Multiple results but exact title match → pick that
                                chosen_jimaku_anime = next(r for r in jimaku_results if r['name'] == series_display_title)
                                print(f"--> [Jimaku] Exact title match found: {chosen_jimaku_anime['name']}")
                            else:
                                print("\n--- Jimaku.cc Search Results ---")
                                for i, anime in enumerate(jimaku_results, 1):
                                    print(f"  [{i}] {anime.get('name')}")
                                try:
                                    jimaku_choice_num = int(input("\nEnter the number of the correct anime (or 0 to skip): "))
                                    if jimaku_choice_num == 0:
                                        print("--> Skipping jimaku search.")
                                        chosen_jimaku_anime = None
                                    elif 0 < jimaku_choice_num <= len(jimaku_results):
                                        chosen_jimaku_anime = jimaku_results[jimaku_choice_num - 1]
                                    else:
                                        print("--> Invalid selection. Skipping Jimaku search.")
                                        chosen_jimaku_anime = None
                                except (ValueError, IndexError): print("--> Invalid selection. Skipping Jimaku search.")
                            
                            # Filter files: Prefer .ass (styled) over .srt to avoid duplicates
                            if chosen_jimaku_anime:
                                files = get_jimaku_files(chosen_jimaku_anime['id'])
                                    
                                files_to_download = [f for f in files if extract_episode_num(f['name']) == chosen_ep['num']]
                                
                                # Get specific formats
                                ass_files = [f for f in files_to_download if f['name'].lower().endswith('.ass')]
                                srt_files = [f for f in files_to_download if f['name'].lower().endswith('.srt')]
                                
                                # Combine them (ASS first, then SRT)
                                target_files = ass_files + srt_files
                                
                                if target_files:
                                    print(f"--> [Jimaku] Found {len(target_files)} subtitle file(s) for episode {chosen_ep['num']}.")
                                    for file_data in target_files:
                                        local_path = download_jimaku_sub(file_data, chosen_jimaku_anime['name'])
                                        if local_path:
                                            mpv_command.append(f'--sub-file={local_path}')
                                            has_jimaku = True
                                else:
                                    print(f"--> [Jimaku] No files found for episode {chosen_ep['num']}.")
                    elif not config.get("enable_jimaku", True):
                        print("-->[Config] enable_jimaku set to 'False'")
                        print("-->[Jimaku] Skipping Jimaku api...")
                    else:
                        print("--> [Jimaku] Skipping. No Jimaku API KEY found in environment variable")
                    if has_jimaku and "Japanese (Jimaku)" not in loaded_subs:
                        loaded_subs.append("Japanese (Jimaku)")
                    
                    # Load stream (English) subs AFTER Jimaku so Japanese is default
                    stream_subs = [track for track in stream_data.get("tracks", []) if track.get("kind") != "thumbnails"]
                    counter = 1
                    for sub in stream_subs:
                        if sub.get('file') and 'english' in sub.get('label', '').lower():
                            srt_converted = download_and_convert_sub(sub.get('file'), counter)
                            if srt_converted:
                                mpv_command.append(f"--sub-file={srt_converted}")
                            else:   
                                mpv_command.append(f"--sub-file={sub.get('file')}")

                            loaded_subs.append(f"{sub.get('label')} (Stream)")
                            counter += 1
                
                    if loaded_subs:
                        print(f"\n--> Loading subtitles: {', '.join(loaded_subs)}")
                    if args.command:
                        print(" ".join(mpv_command))
                        break
                    if launch_and_monitor_mpv(mpv_command):
                        stream_found = True
                        break
                    else:
                        print(f"--> Stream from '{server['name']}' failed viability test. Trying next server...")
            
            if stream_found:
                print("--- Player closed. ---")
            else:
                print("\n\n---FAILED TO FIND SERVER---"); print("--> Could not acquire a working stream from any available server.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n--> Operator interrupt detected. Shutting down.")
        exit()
