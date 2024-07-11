import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler
from telegram.ext.filters import Filters
import libtorrent as lt
import time
import os
import threading
import datetime
import resource

class TorrentDownloader:
    def __init__(self, bot_token):
        self.bot = telegram.Bot(token=bot_token)
        self.updater = Updater(token=bot_token, use_context=True, base_url="http://0.0.0.0:8081/bot")
        self.dispatcher = self.updater.dispatcher
        self.ses = lt.session()
        self.memory_threshold = 900 * 1024 * 1024

    def start(self, update, context):
        update.message.reply_text(f"Hello! Send me a magnet link (just) to start downloading.(v2)")
        
    def handle_torrent(self, update, context):
        self.torr_thread = threading.Thread(target=self.download_torrent, args=(update,context))
        self.torr_thread.start()

    def download_torrent(self, update, context):
        chat_id = update.message.chat_id
        os.system(f"rm -rf {chat_id}/")
        time.sleep(3)
        os.system(f'mkdir {chat_id}/')
        if update.message.document:
            if update.message.document.mime_type == "application/x-bittorrent":
                update.message.reply_text("I JUST can handle Magnet Link.")
                return
        elif update.message.text.startswith("magnet:"):
            params = {
                'save_path': f'./{chat_id}/',
            }
            handle = lt.add_magnet_uri(self.ses, update.message.text, params)
            current_dir = os.listdir(f'./{chat_id}/')
            print('Downloading...')
            c = 0
            message = self.bot.send_message(chat_id=chat_id, text='Start Downloading...')
            last_progress_message = ''
            while not handle.is_seed():
                s = handle.status()
                time.sleep(1)
                progress_message = '%.2f%% complete (down: %.1f kB/s up: %.1f kB/s peers: %d)' % (s.progress * 100, s.download_rate / 1000, s.upload_rate / 1000, s.num_peers)
                print(progress_message)
                if progress_message != last_progress_message:
                    try:
                        self.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=progress_message)
                        last_progress_message = progress_message
                    except telegram.error.RetryAfter as e:
                        with open('log.log','a') as log:
                            now = datetime.datetime.now()
                            log.write(f'{now} - Error: {e}%\n')
                        time.sleep(e.retry_after + 2)
                        last_progress_message = progress_message
                        continue

                if c > 30 and s.progress == 0:
                    update.message.reply_text("torrent has no seed and could not be download, try another one.")
                    return
                c += 1
            time.sleep(1)
            new_dirs = os.listdir(f'./{chat_id}/')
            new_dir = list(set(new_dirs) - set(current_dir))
            if new_dir:
                name = new_dir[0]
            else:
                return
            with open('History.txt','a') as log:
                now = datetime.datetime.now()
                log.write(f'{now} -> UserID: {chat_id} - MovieName: {name}\n')

        # Find the media file inside the downloaded directory
        downloaded_directory = os.path.join(f'./{chat_id}/', name)
        if os.path.isdir(downloaded_directory):
            media_files = self.find_media_file(downloaded_directory)
        elif os.path.isfile(downloaded_directory):
            media_files = downloaded_directory

        if isinstance(media_files,list):
            if len(media_files) == 1:
                media_file = media_files[0]
                try:
                    update.message.reply_chat_action(telegram.constants.CHATACTION_UPLOAD_DOCUMENT)
                    with open(media_file, 'rb') as f:
                        update.message.reply_document(f)
                        time.sleep(20)
                except Exception as e:
                    print("ERROR:(1):",e)
                    update.message.reply_text("✅ Maybe we have problem in sending file😐, if you did not recieve any file after about 5 min. try again later.🔄")
            elif len(media_files) > 1:
                media_files.sort()
                update.message.reply_text(f"All right. We download {len(media_files)} files and now sending them to you. Be patient!😊")
                update.message.reply_chat_action(telegram.constants.CHATACTION_UPLOAD_DOCUMENT)
                for media in media_files:
                    try:
                        with open(media, 'rb') as f:
                            try:
                                update.message.reply_document(f)
                                time.sleep(20)
                            except telegram.error.RetryAfter as e:
                                time.sleep(e.retry_after + 2)
                                update.message.reply_document(f)
                                time.sleep(20)
                    except Exception as e:
                        print("ERROR:(1):",e)
            else:
                update.message.reply_text("No media file found in the downloaded directory. We only download media torrents.")
                self.ses.remove_torrent(handle)
        elif isinstance(media_files,str):
            try:
                update.message.reply_chat_action(telegram.constants.CHATACTION_UPLOAD_DOCUMENT)
                with open(media_files, 'rb') as f:
                    update.message.reply_document(f)
                    time.sleep(20)
            except Exception as e:
                print("ERROR:(1):",e)
                update.message.reply_text("✅ Maybe we have problem in sending file😐, if you did not recieve any file after about 5 min. try again later.🔄")
                

    def find_media_file(self,directory):
        print("finding media")
        for root, dirs, files in os.walk(directory):
            file_list = []
            for file in files:
                # Check if the file is a media file (you can customize this condition as needed)
                if file.endswith(('.mp4', '.mkv', '.avi', '.zip','.srt')):
                     file_list.append(os.path.join(root, file))
            return file_list
        # return None
    
    def get_memory_usage(self):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    
    def main(self):
        self.swap = threading.Thread(target=self.check_swap)
        self.swap.start()
        self.rem_temp = threading.Thread(target=self.remove_dir)
        self.rem_temp.start()

        self.dispatcher.add_handler(CommandHandler("start", self.start))
        self.dispatcher.add_handler(MessageHandler(Filters.document.mime_type("application/x-bittorrent"), self.handle_torrent))
        self.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handle_torrent))

        self.updater.start_polling()
        self.updater.idle()

    def check_swap(self):
        while True:
            time.sleep(1)
            with open('/proc/meminfo','r') as mem_info:
                for line in mem_info:
                    if line.startswith('SwapTotal:'):
                        total = int(line.split()[1])
                    elif line.startswith('SwapFree:'):
                        free = int(line.split()[1])
                free_perc = (free * 100)/total
            if free_perc < 65:
                with open('log.log','a') as log:
                    now = datetime.datetime.now()
                    log.write(f'{now} - FreeSwap: {free_perc}%\n')
                if hasattr(self,'torr_thread'):
                    if not self.torr_thread.is_alive():
                        os.system('swapoff -a;swapon -a')
                else:
                    os.system('swapoff -a;swapon -a')
            if self.get_memory_usage() > self.memory_threshold:
                if hasattr(self,'torr_thread'):
                    if not self.torr_thread.is_alive():
                        os._exit(1)
                else:
                    os._exit(1)

    def remove_dir(self):
        while True:
            time.sleep(30)
            if hasattr(self,'torr_thread'):
                if not self.torr_thread.is_alive():
                    list_dir = os.listdir('.')
                    for dir in list_dir:
                        lastm = os.path.getmtime(dir)
                        diff = time.time() - lastm
                        if diff > 2700:
                            os.system(f'rm -rf {dir}/')
                            time.sleep(1)
            else:
                list_dir = os.listdir('.')
                for dir in list_dir:
                    lastm = os.path.getmtime(dir)
                    diff = time.time() - lastm
                    if diff > 2700:
                        os.system(f'rm -rf {dir}/')
                        time.sleep(1)

if __name__ == '__main__':
    bot_token = "BOT_TOKEN"
    downloader = TorrentDownloader(bot_token)
    downloader.main()
