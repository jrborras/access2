#!/usr/bin/env python3
import os
import json
import time
import threading
import logging
import requests
from telegram import telegram_send_message

import paho.mqtt.client as mqtt

# Logging configuration
mode = os.environ.get("DEBUGMODE", "DEBUG")
if mode == "DEBUG":
    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y/%m/%d %H:%M:',
        level=logging.DEBUG
    )
else:
    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y/%m/%d %H:%M:',
        level=logging.INFO
    )

# MQTT Variables
MQTT_ADDRESS = os.environ.get("MQTT_ADDRESS", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWD = os.environ.get("MQTT_PASSWD", "")

# Topics variables
DOOR_TOPIC = os.environ.get("DOOR_TOPIC", "")
ACCESS_TOPIC = os.environ.get("ACCESS_TOPIC", "")
ACCESS_TOPIC_STATUS = os.environ.get("ACCESS_TOPIC_STATUS", "")
ACCESS_COMMAND = os.environ.get("ACCESS_COMMAND", "")
ACCESS_BUTTON = os.getenv('ACCESS_BUTTON', "")
ACCESS_BUTTON_PAYLOAD = os.getenv('ACCESS_BUTTON_PAYLOAD', "")

# Other variables
TRIGGER_TIME = int(os.environ.get("TRIGGER_TIME", 30))
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHATID = os.environ.get("TELEGRAM_CHATID", "")

# The list of the permitted users is stored in a json file
# At first, the variable should be initialized to None
ALLOWED_USERS = None

# Duration of alarm signal (in seconds) before resetting to armed mode
ALARM_DURATION = TRIGGER_TIME

# System statuses:
# "disarmed" -> system disarmed (red led on, green led off)
# "armed" -> system armed (red led off, green led on)
# "button_pending" -> button pressed; during TRIGGER_TIME openings are ignored (green led flashing)
# "trigger_pending" -> door open in armed mode; during TRIGGER_TIME NFC is expected to cancel the alarm (red led flashing, green led on)
# "alarm" -> alarm generated (both leds flashing and Telegram message sent)
class SecuritySystem:
    def __init__(self):
        self.system_state = "disarmed"
        self.state_lock = threading.RLock()
        self.trigger_timer = None
        self.button_timer = None
        self.alarm_timer = None

        self.mqtt_client = mqtt.Client()

        if MQTT_USER:
            self.mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWD)

        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message

    # Connection and subscription to the topics
    def start(self):
        try:
            self.mqtt_client.connect(MQTT_ADDRESS, MQTT_PORT, keepalive=60)
        except Exception as e:
            logging.error("Error connecting to MQTT broker: %s", e)
            return

        # Start a loop in a thread so that it does not block
        self.mqtt_client.loop_start()

        # Pi=ublish the initial state
        self.publish_system_state()
        # Set LED to initial state (disarmed: red LED on, green LED off)
        self.send_led_command({"power1": "on", "power2": "off", "buzzer": "1,1,1,1"})

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Exiting...")
        finally:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

    # Callback when connected
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT broker")
            client.subscribe(DOOR_TOPIC)
            client.subscribe(ACCESS_TOPIC)
            client.subscribe(ACCESS_BUTTON)
        else:
            logging.error("Error in MQTT connection. Code: %s", rc)

    # Callback to receive a message
    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode("utf-8")
            data = json.loads(payload)
        except Exception as e:
            logging.error("Error decoding message: %s", e)
            return

        topic = msg.topic
        logging.debug("Message received in: %s: %s", topic, data)

        if topic == DOOR_TOPIC:
            self.process_door_message(data)
        elif topic == ACCESS_TOPIC or ACCESS_BUTTON:
            self.process_access_message(data)
        else:
            logging.warning("Message in unknown topic: %s", topic)

    # Processes messages from the door sensor
    def process_door_message(self, data):
        # The JSON is expected to contain the key "contact"
        if "contact" not in data:
            return

        door_closed = data["contact"]
        with self.state_lock:
            current_state = self.system_state

        if current_state == "armed":
            if not door_closed:
                logging.info("Door open in armed mode. Starting alarm timer (%s s)", TRIGGER_TIME)
                self.start_trigger_timer()
            else:
                # If the door is closed, the pending timer may be cancelled (optional)
                logging.info("Door closed in armed mode.")
        else:
            # In disarmed or button_pending mode openings are ignored
            logging.debug("Door open in mode '%s'. Ignored.", current_state)

    # Processes access control messages (NFC or button)
    def process_access_message(self, data):
        # First, it is detected if it is the button
        if ACCESS_BUTTON_PAYLOAD in data and data[ACCESS_BUTTON_PAYLOAD] == "ON":
            with self.state_lock:
                if self.system_state == "disarmed":
                    logging.info("Button pressed in disarmed mode. Starting ignore period (%s s)", TRIGGER_TIME)
                    self.start_button_timer()
            return

        # Now, the NFC is processed (the structure is expected: {"PN532": {"UID": "xxxx"}})
        if "PN532" in data and "UID" in data["PN532"]:
            uid = data["PN532"]["UID"]
            logging.info("NFC card read. UID: %s", uid)
            # Check if the user is valid
            if any(user["uid"].lower() == uid.lower() for user in ALLOWED_USERS):
                logging.info("Access allowed for UID %s", uid)
                
                with self.state_lock:
                    # If you are in the cancellation waiting state or the alarm has already been activated, cancel and move to disarm.
                    if self.system_state == "trigger_pending":
                        self.cancel_trigger_timer()
                        self.set_state("disarmed")
                        self.send_led_command({"power1": "on", "power2": "off", "buzzer": "1,1,1,1"})
                        self.publish_system_state()
                        logging.info("Alarm cancelled by valid NFC. System disarmed.")
                    elif self.system_state == "alarm":
                        if self.alarm_timer is not None:
                            self.alarm_timer.cancel()
                            self.alarm_timer = None
                        self.set_state("disarmed")
                        self.send_led_command({"power1": "on", "power2": "off", "buzzer": "1,1,1,1"})
                        self.publish_system_state()
                        logging.info("Alarm cancelled by valid NFC. System disarmed.")
                    else:
                        logging.info("NFC read but system is not in alarm state (status: %s)", self.system_state)
                        self.set_state("disarmed")
                        self.send_led_command({"power1": "on", "power2": "off", "buzzer": "1,1,1,1"})
                        self.publish_system_state()
            else:
                logging.warning("Access denied for UID %s", uid)

    # Starts the timer when the door is opened in armed mode
    def start_trigger_timer(self):
        with self.state_lock:
            if self.system_state != "armed":
                return  # If not armed, opening is not processed
            # Change to pending cancellation status
            self.set_state("trigger_pending")
        # LED switch: red LED flashes, green LED on
        self.send_led_command({"power1": "blink", "power2": "on", "buzzer": "1,1,1,1"})
        # Start the timer
        self.trigger_timer = threading.Timer(TRIGGER_TIME, self.trigger_alarm)
        self.trigger_timer.start()

    # Cancel the pending alarm timer
    def cancel_trigger_timer(self):
        if self.trigger_timer is not None:
            self.trigger_timer.cancel()
            self.trigger_timer = None

    # When the button is pressed in disarm mode
    def start_button_timer(self):
        with self.state_lock:
            self.set_state("button_pending")
        # Update LED: Red LED off, Green LED flashing
        self.send_led_command({"power1": "off", "power2": "blink", "buzzer": "1,1,1,1"})
        self.button_timer = threading.Timer(TRIGGER_TIME, self.end_button_timer)
        self.button_timer.start()

    # Ends the period after pressing the button and arms the system
    def end_button_timer(self):
        with self.state_lock:
            self.set_state("armed")
        self.send_led_command({"power1": "off", "power2": "on", "buzzer": "1,1,1,1"})
        self.publish_system_state()
        logging.info("End of ignore period. System armed.")

    # Timer callback: alarm is triggered if door opening has not been cancelled
    def trigger_alarm(self):
        with self.state_lock:
            # Alarm is only generated if the system is still in trigger_pending state
            if self.system_state != "trigger_pending":
                return
            self.set_state("alarm")
        logging.warning("Alarm activated! The alarm was not cancelled in time.")
        # Update LED: both LEDs flash and the buzzer is activated
        self.send_led_command({"power1": "blink", "power2": "blink", "buzzer": "1,1,1,1"})
        # Send message to Telegram
        self.send_telegram_message("Alarm: door opened without authorization.")

        # After ALARM_DURATION the alarm is reset and returns to armed mode
        self.alarm_timer = threading.Timer(ALARM_DURATION, self.reset_alarm)
        self.alarm_timer.start()

    # Reset the alarm and return to armed mode
    def reset_alarm(self):
        with self.state_lock:
            self.set_state("armed")
        self.send_led_command({"power1": "off", "power2": "on", "buzzer": "1,1,1,1"})
        self.publish_system_state()
        logging.info("Alarm terminated. System re-armed.")

    # Send an LED command via MQTT to the ACCESS_COMMAND topic
    def send_led_command(self, command_dict):
        try:
            payload = json.dumps(command_dict)
            self.mqtt_client.publish(ACCESS_COMMAND, payload)
            logging.debug("LED command sent: %s", payload)
        except Exception as e:
            logging.error("Error sending LED command: %s", e)

    # Publish the current status of the system to the ACCESS_TOPIC topic
    def publish_system_state(self):
        state_msg = {}
        with self.state_lock:
            if self.system_state in ["armed", "trigger_pending", "alarm"]:
                state_msg = {"system": "armed"}
            elif self.system_state in ["disarmed", "button_pending"]:
                state_msg = {"system": "disarmed"}
        try:
            payload = json.dumps(state_msg)
            self.mqtt_client.publish(ACCESS_TOPIC_STATUS, payload)
            logging.info("System status published: %s", payload)
        except Exception as e:
            logging.error("Error publishing system status: %s", e)

    # Send message to Telegram
    def send_telegram_message(self, text):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHATID:
            logging.warning("Telegram not configured. Message not sent.")
            return
        try:
            response = telegram_send_message(TELEGRAM_CHATID, TELEGRAM_TOKEN, "ALARM: the door has been opened with the alarm connected!!!")
            if response.status_code == 200:
                logging.info("Telegram message sent successfully.")
            else:
                logging.error("Error sending Telegram message: %s", response.text)
        except Exception as e:
            logging.error("Exception when sending message to Telegram: %s", e)
        
    def set_state(self, new_state):
        with self.state_lock:
            logging.info("Status change: %s -> %s", self.system_state, new_state)
            self.system_state = new_state
            
# Load the list of users from users.json file
def load_users():
    try:
        with open('users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.debug("Error: File users.json not found")
        exit(1)
    except json.JSONDecodeError:
        logging.debug("Error: Invalid format in users.json")
        exit(1)

if __name__ == "__main__":
    ALLOWED_USERS = load_users()
    security_system = SecuritySystem()
    security_system.start()
