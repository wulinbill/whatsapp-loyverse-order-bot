from flask import Flask, request, abort
from twilio.twiml.messaging_response import MessagingResponse
import logging, os
from deepgram_utils import transcribe_audio
from agent import handle_message

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    sessions={}
    @app.route("/sms", methods=["POST"])
    def sms():
        from_num=request.form.get("From")
        body=request.form.get("Body","").strip()
        num_media=int(request.form.get("NumMedia","0"))
        if num_media>0 and not body:
            ctype=request.form.get("MediaContentType0","")
            if ctype.startswith("audio"):
                body=transcribe_audio(request.form.get("MediaUrl0"))
        if not body:
            abort(400,"Empty message")
        hist=sessions.setdefault(from_num,[])
        reply=handle_message(from_num, body, hist)
        twiml=MessagingResponse()
        twiml.message(reply)
        return str(twiml),200,{"Content-Type":"application/xml"}
    return app
