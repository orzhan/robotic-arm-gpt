import os
import time
import platform
import json
import pickle
import base64
import io
import numpy as np
from pathlib import Path
import httpx
import anthropic
from openai import OpenAI

# Local imports
from robot import init_sdk, init_components, move_servo, move_servo_slow, move_two_servos_sync, execute_string_command
from webcamera import WebcamCapture
from tts import OpenAITTSQueue
from stt import WhisperCommandQueue
from util import image_to_uri, encode_credentials
from prompt import system_prompt_simple

anthropic_key = "sk-ant-KEY"
username = 'P'
password = 'P'
encoded_username, encoded_password = encode_credentials(username, password)
proxy_url = f"http://{encoded_username}:{encoded_password}@1.1.1.1:3128"
client = anthropic.Anthropic(http_client=httpx.Client(proxy=proxy_url), api_key=anthropic_key)
openai_client = OpenAI(api_key="sk-KEY", http_client=httpx.Client(proxy=proxy_url))

webcam = WebcamCapture(camera_index=1)
webcam.get_video_frame()

tts_queue = OpenAITTSQueue(openai_client)

init_sdk()
servos = init_components()
move_servo(servos[0], 1450)
move_servo(servos[1], 1825)
move_servo(servos[2], 1450)
move_servo(servos[6], 1950)

move_two_servos_sync(servos, 1450, 1825, 1450)
move_servo_slow(servos[6], 1950)


try:
    command_queue = WhisperCommandQueue(tts_queue)
    
    while True:
        command = command_queue.get_command(timeout=1.0)
        
        if command:
            print(f"Processing command: {command.text}")
            command_queue.pause()
            instruction = command.text
    
            message_history = []
            message_history_full = []
            for step in range(10):
                image = webcam.get_video_frame()
            
                for old_step in range(0, len(message_history)):
                    if message_history[old_step]['role'] == 'user':
                        message_history[old_step]['content'] = '[IMAGE]'
            
                user_message = {
                                      "role": "user",
                                      "content": [
                                        {
                                          "type": "image",
                                          "source": {
                                              "type": "base64",
                                              "media_type": "image/png",
                                              "data":  image_to_uri(np.array(image))
                                          },
                                        },
                                      ],
                                    }
                if step == 0:
                    user_message["content"].insert(0, {"type": "text", "text": f"<instruction>{instruction}</instruction>"})
                message_history.append(user_message)
                message_history_full.append(message_history[-1].copy())
                message = client.messages.create(
                                #model="claude-3-5-sonnet-20241022",
                                model="claude-3-5-sonnet-20240620",
                                system=system_prompt_simple,
                                messages=message_history,
                                max_tokens=1000,
                                temperature=0.5
                            )
                t = message.content[0].text
                print(t)
                message_history.append({"role": "assistant", "content": t})
                message_history_full.append(message_history[-1].copy())
                t = t[t.find("{"):]
                t = t[:t.rfind("}")+1]
                try:
                    r = json.loads(t, strict=False)
                    tts_queue.add_text(r["reasoning_ru"], speed=1.1)
                    for a in r["actions"]:
                        execute_string_command(a["target_square"], a["target_arm_height"], a["gripper"])
                        time.sleep(0.5)
                    if len(r["actions"]) == 0:
                        break
                    tts_queue.wait_until_done() 
                    time.sleep(1.5)
                except KeyboardInterrupt:
                    break
                except Exception as ex:
                    print(ex)
            command_queue.resume()

        time.sleep(0.1)
        
except KeyboardInterrupt:
    print("\nShutting down...")
except Exception as ex:
    print(f"Fatal error: {ex}")
finally:
    if 'command_queue' in locals():
        command_queue.stop()
    tts_queue.clear_queue()
    move_two_servos_sync(servos, 1500, 1750, 1750)
    move_servo(servos[6], 1950)


with open("robotic-experiment-history.pkl","wb") as f:
    pickle.dump(message_history_full, f)
