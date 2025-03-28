from flask import Flask, request, jsonify
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import librosa
from models import build_model
import torch
import numpy as np
from onnxruntime import InferenceSession
import soundfile as sf
from kokoro import phonemize, tokenize
import os
import uuid
import logging
from flask_cors import CORS
# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Paths for T2S
model_path = 'kokoro-v0_19.pth'
onnx_path = 'kokoro-v0_19.onnx'
voice_name = 'am_adam'  # Voice: Adam
voicepack_path = f'voices/{voice_name}.pt'

# Load T2S model and assets during startup
try:
    logger.info("Loading T2S model...")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.debug(f"Using device: {device}")
    model = build_model(model_path, device)
    logger.info(f"T2S model loaded successfully from {model_path}")

    logger.info("Loading voicepack...")
    voicepack = torch.load(voicepack_path)
    logger.info(f"Voicepack loaded successfully from {voicepack_path}")

    logger.info("Loading ONNX session...")
    sess = InferenceSession(onnx_path)
    logger.info(f"ONNX session loaded successfully from {onnx_path}")
except Exception as e:
    logger.error(f"Error during T2S model initialization: {str(e)}")
    raise

# Initialize Whisper model for S2T
try:
    logger.info("Loading Whisper model for S2T...")
    processor = WhisperProcessor.from_pretrained("openai/whisper-small")
    whisper_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-small")
    whisper_model.config.forced_decoder_ids = None
    logger.info("Whisper model loaded successfully")
except Exception as e:
    logger.error(f"Error during Whisper model initialization: {str(e)}")
    raise


@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    """Text-to-Speech (T2S) Endpoint"""
    try:
        logger.debug("Received request to /generate_audio")
        data = request.json
        text = data['text']
        output_path = data.get('output', 'output_audio.wav')
        logger.debug(f"Text: {text}")
        logger.debug(f"Output path: {output_path}")

        # Tokenize text
        logger.debug("Tokenizing text...")
        tokens = tokenize(phonemize(text, 'a'))
        logger.debug(f"Initial tokens: {tokens}")
        if len(tokens) > 510:
            logger.warning(f"Text too long; truncating to 510 tokens.")
            tokens = tokens[:510]
        tokens = [[0, *tokens, 0]]
        logger.debug(f"Final tokens: {tokens}")

        # Get voicepack style
        logger.debug("Fetching voicepack style...")
        style = voicepack[len(tokens[0]) - 2].numpy()
        logger.debug(f"Voicepack style shape: {style.shape}")

        # Run ONNX inference
        logger.debug("Running ONNX inference...")
        audio = sess.run(None, dict(
            tokens=tokens,
            style=style,
            speed=np.ones(1, dtype=np.float32)
        ))[0]
        logger.debug(f"Audio generated with shape: {audio.shape}")

        # Save audio
        logger.debug(f"Saving audio to {output_path}...")
        sf.write(output_path, audio, 24000)
        logger.info(f"Audio saved successfully to {output_path}")
        return jsonify({"status": "success", "output_path": output_path})
    except Exception as e:
        logger.error(f"Error generating audio: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/transcribe_audio', methods=['POST'])
def transcribe_audio():
    """Speech-to-Text (S2T) Endpoint"""
    try:
        logger.debug("Received request to /transcribe_audio")
        file = request.files['file']
          # Generate a unique filename using uuid
        unique_filename = f"{uuid.uuid4().hex}_{file.filename}"
        audio_path = os.path.join("/tmp", unique_filename)
        file.save(audio_path)
        logger.debug(f"Audio file saved to {audio_path}")

        # Load and preprocess audio
        logger.debug("Processing audio for transcription...")
        audio_array, sampling_rate = librosa.load(audio_path, sr=16000)
        input_features = processor(
            audio_array,
            sampling_rate=sampling_rate,
            return_tensors="pt"
        ).input_features

        # Generate transcription
        logger.debug("Generating transcription...")
        predicted_ids = whisper_model.generate(input_features)
        transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
        logger.info(f"Transcription: {transcription}")

        return jsonify({"status": "success", "transcription": transcription})
    except Exception as e:
        logger.error(f"Error transcribing audio: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        os.remove(audio_path)

if __name__ == '__main__':
    logger.info("Starting Flask server on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000)

