import asyncio
import base64
import json
import os
import pyaudio
import pandas as pd
from websockets.client import connect
from dotenv import load_dotenv
from gtts import gTTS
from googletrans import Translator
import tempfile
import pyttsx3

# Load environment variables
load_dotenv("api_key.env")

# Load the market prices dataset
#market_prices_df = pd.read_csv("data/market_prices.csv")

class SimpleGeminiVoice:
    def __init__(self):
        self.audio_queue = asyncio.Queue()
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model = "gemini-2.0-flash-exp"
        self.uri = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={self.api_key}"
        # Audio settings
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.CHUNK = 512
        self.RATE = 16000
        self.model_speaking = False
        self.running = True  # Flag to control the running state

    async def start(self):
        # Initialize websocket
        self.ws = await connect(
            self.uri,
            extra_headers={"Content-Type": "application/json"}
        )
        await self.ws.send(json.dumps({"setup": {"model": f"models/{self.model}"}}))
        await self.ws.recv()
        print("Connected to Gemini, You can start talking now")
        
        # Use asyncio.gather to run tasks concurrently
        tasks = [
            asyncio.create_task(self.capture_audio()),
            asyncio.create_task(self.stream_audio()),
            asyncio.create_task(self.play_response())
        ]
    
    async def capture_audio(self):
        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
        )

        while self.running:  # Continue capturing if running is True
            data = await asyncio.to_thread(stream.read, self.CHUNK)
            # Only send audio when model is not speaking
            if not self.model_speaking:
                await self.ws.send(json.dumps({
                    "realtime_input": {
                        "media_chunks": [{
                            "data": base64.b64encode(data).decode(),
                            "mime_type": "audio/pcm",
                        }]
                    }
                }))

    async def stream_audio(self):
        async for msg in self.ws:
            response = json.loads(msg)
            try:
                audio_data = response["serverContent"]["modelTurn"]["parts"][0]["inlineData"]["data"]
                if not self.model_speaking:
                    self.model_speaking = True
                    print("\nModel started speaking")
                self.audio_queue.put_nowait(base64.b64decode(audio_data))
            except KeyError:
                pass
            
            try:
                turn_complete = response["serverContent"]["turnComplete"]
            except KeyError:
                pass
            else:
                if turn_complete:
                    print("\nEnd of turn")
                    # Wait a bit to ensure all audio is processed
                    await asyncio.sleep(0.5)
                    while not self.audio_queue.empty():
                        self.audio_queue.get_nowait()
                    self.model_speaking = False
                    print("Ready for next input")

    
    
    async def play_response(self):
        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=24000,
            output=True
        )
        try:
            while self.running:
                data = await self.audio_queue.get()
                await asyncio.to_thread(stream.write, data)
        except asyncio.CancelledError:
            print("play_response cancelled")
            stream.stop_stream()
            stream.close()


    def stop(self):
        # Stop all the processes
        print("Stopping all tasks...")
        self.running = False

    async def stop_tasks(self):
        # Gracefully cancel tasks
        await self.ws.close()  # Close the websocket
        print("WebSocket connection closed.")
        self.stop()  # Stop running flag to break out of loops

    def get_market_price(self, product, location=None):
        """
        This function queries the dataset for the price of a product. If a location is provided, it filters by location.
        """
        filtered_data = market_prices_df[market_prices_df['product'].str.contains(product, case=False, na=False)]
        
        if location:
            filtered_data = filtered_data[filtered_data['location'].str.contains(location, case=False, na=False)]
        
        if not filtered_data.empty:
            price = filtered_data.iloc[0]['price']
            return f"The price of {product} in {location if location else 'your area'} is {price}."
        else:
            return f"Sorry, I couldn't find the price of {product}."

    async def fetch_schemes_and_info(self, query):
        """
        This function will send the user query to the Gemini API to fetch government schemes or other information.
        """
        try:
            await self.ws.send(json.dumps({
                "realtime_input": {
                    "text": {
                        "text": query
                    }
                }
            }))
        except Exception as e:
            print(f"Error during Gemini API request: {e}")

    async def handle_text_query(self, query):
        await self.start()
        await self.fetch_schemes_and_info(query)
        await asyncio.sleep(2)  # allow time for Gemini to respond

        # Get the last response from Gemini (you may need to save it during stream_audio)
        return "Example Gemini reply: Here is the info you requested."  # Replace with actual logic


    async def handle_query(self, query):
        
        if query.lower() in ["stop", "exit", "band karo", "close", "ನಿಲ್ಲಿಸಿ", "बंद करो","நிறுத்து","ఆపు"]:
            print("Stop command received. Shutting down.")
            await self.stop_tasks()
            return
        """
        This function interprets the user query and checks if it's a market price query or a general query.
        """
        if "price" in query.lower() and ("of" in query.lower() or "for" in query.lower()):
            # Extract product and location
            words = query.split()
            product = None
            location = None
            
            for word in words:
                if word.lower() in ['wheat', 'rice', 'potato']:  # Add more products as needed
                    product = word.lower()
                if word.lower() in ['karnataka', 'kerala', 'up', 'maharashtra']:  # Add locations as needed
                    location = word.lower()
            
            if product:
                response = self.get_market_price(product, location)
            else:
                response = "Sorry, I couldn't understand which product you're asking for."
            print(response)  # Output price response
            await self.fetch_schemes_and_info(f"Tell me about schemes for {product} in {location or 'general area'}")
        
        else:
            # If it's not about price, ask Gemini for more info
            print("Fetching information from Gemini...")
            await self.fetch_schemes_and_info(query)

if __name__ == "_main_":
    client = SimpleGeminiVoice()

    # Start the client
    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:
        print("\nUser interrupted. Stopping...")
        asyncio.run(client.stop_tasks())  # Gracefully stop everything

    # Example: simulate a query about the price of rice in Karnataka and schemes related to rice
    # asyncio.run(client.handle_query("What is the price of rice in Karnataka?"))


def speak(text, lang='hi'):  # 'hi' for Hindi, 'kn' for Kannada, etc.
    tts = gTTS(text=text, lang=lang)
    with tempfile.NamedTemporaryFile(delete=True, suffix=".mp3") as fp:
        tts.save(fp.name)
        os.system(f'start {fp.name}')  # works on Windows