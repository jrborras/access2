# MQTT-Based Security System with NFC and Telegram Integration

A Python security system that monitors door status through MQTT, controls access via NFC tags, and sends alerts through Telegram. Features LED status indicators and configurable trigger times.

## Project Structure

```
access2/
├── app/app.py              # Main application logic
├── app/requirements.txt    # Python dependencies (pyserial, paho-mqtt)
├── app/users.json          # Authorized NFC users
├── app/telegram.json       # Telegram function
├── .env                    # Environment variables for MQTT configuration
├── Dockerfile              # Dockerfile to build the Python container
├── docker-compose.yml      # Docker Compose file to run the container
└── README.md               # Project documentation
```

## Features

- 🚪 Real-time door status monitoring via MQTT
- 🔑 NFC-based access control with authorized users list
- 🔴🟢 Visual indicators using LED lights
- ⏲️ Configurable security trigger timeout
- 📱 Telegram notifications for security events
- 🔄 Asynchronous operation using threading

## Prerequisites

- Python 3.12
- MQTT Broker (e.g., Mosquitto)
- Telegram Bot Token
- Physical Devices:
  - Door contact sensor (MQTT-enabled)
  - NFC reader (MQTT-enabled)
  - LED indicators (controllable via MQTT)

The door contact sensor in my case, is a Zigbee device. I'm running a zigbee2mqtt container, which receives the messages from the sensor, and published in the MQTT broker.

The NFC reader, is a ESP32 device with a PN532 NFC reader. The firmware installed on the ESP32 device is [Tasmota](https://tasmota.github.io/docs/PN532/).

## Installation

Clone the repository:
```bash
git clone https://github.com/jrborras/access2.git
cd access2
```


## Configuration

1. Create `.env` file:
```ini
# General variables
TIME_ZONE=Europe/Madrid
DEBUG_MODE_DEV=debug

# MQTT Variables 
MQTT_ADDRESS=mosquitto_broker
MQTT_PORT=1883
MQTT_USER=mqtt_user
MQTT_PASSWD=mqtt_password
MQTT_ACCESS2_CLIENT=ClientAccess2

# Telegram Variables
TELEGRAM_TOKEN=123456789:telegram-token-example
TELEGRAM_CHATID=-123456789

# access2 Variables
DOOR_TOPIC=zigbee2mqtt/door
ACCESS_TOPIC=home/access2/SENSOR
ACCESS_TOPIC_STATUS=home/access2/STATUS
ACCESS_COMMAND=home/access2/cmnd/json
ACCESS_BUTTON=home/access2/RESULT
ACCESS_BUTTON_PAYLOAD=POWER3
TRIGGER_TIME=45
```

2. Set up `users.json`:
```json
[
    {
        "name": "user1",
        "uid": "3456AC5A"
    },
    {
        "name": "user2",
        "uid": "12345ABC"
    },
    {
        "name": "user3",
        "uid": "ACE87653"
    }
]
```

## Usage

1. System states:
- **Armed** (Green LED on):
  - Door opening triggers alarm
  - Valid NFC scan disarms system
- **Disarmed** (Red LED on):
  - No alarm triggering
  - Button press initiates arming sequence

2. LED Indicators:
- 🔴 Red LED: System disarmed
- 🟢 Green LED: System armed
- 🔴 Blinking Red: Alarm triggered
- 🟢 Blinking Green: Arming countdown

### Build and Run

1. **Build the Docker image**:
   
   ```bash
   docker-compose build
   ```

2. **Run the container**:

   ```bash
   docker-compose up -d
   ```

3. **Stop the container**:

   ```bash
   docker-compose down
   ```


## License

MIT License. See `LICENSE` for details.

## Acknowledgements

- [Paho MQTT Client](https://pypi.org/project/paho-mqtt/)
- [Python Requests](https://docs.python-requests.org/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Tasmota](https://tasmota.github.io/docs/)

---