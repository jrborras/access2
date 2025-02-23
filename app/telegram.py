import requests
import logging
import os

telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
telegram_chatid = os.environ.get("TELEGRAM_CHATID", "")

logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s', 
    datefmt='%Y/%m/%d %H:%M:', 
    level=os.environ.get("DEBUGMODE", "INFO")
)

def telegram_send_message(chat_id, token, text):
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {
                'chat_id': chat_id,
                'text': text
                }
    
    r = requests.post(url,json=payload)

    return r

if __name__ == "__main__":
    response = telegram_send_message(telegram_chatid, telegram_token, 'test')
    logging.info(response)
