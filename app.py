import os
import json
from datetime import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# ── Configuración desde variables de entorno ──────────────────────────────────
TWILIO_ACCOUNT_SID     = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN      = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # ej: whatsapp:+14155238886
SPREADSHEET_ID         = os.environ.get("SPREADSHEET_ID")
GOOGLE_CREDS_JSON      = os.environ.get("GOOGLE_CREDS_JSON")  # contenido del JSON como string

# ── Números de los usuarios ───────────────────────────────────────────────────
USUARIOS = {
    "whatsapp:+5491169667092": "Ariel",
    "whatsapp:+5491165297726": "Anto",
}

def notificar_otro(sender, mensaje):
    """Manda un mensaje al otro usuario."""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        for numero, nombre in USUARIOS.items():
            if numero != sender:
                client.messages.create(
                    from_=TWILIO_WHATSAPP_NUMBER,
                    to=numero,
                    body=mensaje
                )
    except Exception as e:
        print(f"ERROR notificando: {e}")

# ── Conexión a Google Sheets ──────────────────────────────────────────────────
def get_sheet():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1
    return sheet

# ── Webhook principal ─────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.form.get("Body", "").strip().lower()
    sender       = request.form.get("From", "")          # whatsapp:+549...
    profile_name = request.form.get("ProfileName", "")   # nombre en WhatsApp

    resp = MessagingResponse()
    msg  = resp.message()

    try:
        sheet = get_sheet()

        # ── COMANDO: listado ──────────────────────────────────────────────────
        if incoming_msg in ["listado", "lista", "ver lista", "ver listado"]:
            rows = sheet.get_all_values()
            # rows[0] es el encabezado, rows[1:] son los productos
            productos = [r[0] for r in rows[1:] if r[0].strip()]

            if not productos:
                msg.body("🛒 La lista está vacía. Mandame productos para agregar!")
            else:
                lista_texto = "\n".join(f"• {p.capitalize()}" for p in productos)
                msg.body(f"🛒 *Lista del Super* ({len(productos)} items):\n\n{lista_texto}")

        # ── COMANDO: borrar / limpiar ─────────────────────────────────────────
        elif incoming_msg in ["borrar", "borrar lista", "limpiar", "limpiar lista", "vaciar"]:
            # Borra todo excepto el encabezado
            all_rows = sheet.get_all_values()
            if len(all_rows) > 1:
                sheet.delete_rows(2, len(all_rows))
            quien = USUARIOS.get(sender, "Alguien")
            msg.body("🗑️ Lista borrada! Podés empezar de nuevo.")
            notificar_otro(sender, f"🗑️ *{quien}* borró la lista del super.")

        # ── COMANDO: ayuda ────────────────────────────────────────────────────
        elif incoming_msg in ["ayuda", "help", "comandos"]:
            msg.body(
                "📋 *Comandos disponibles:*\n\n"
                "• Mandá cualquier producto para agregarlo _(ej: leche, pan, aceite)_\n"
                "• *listado* → ver todos los productos\n"
                "• *borrar* → vaciar la lista\n"
                "• *ayuda* → ver este mensaje"
            )

        # ── AGREGAR PRODUCTO ──────────────────────────────────────────────────
        else:
            # Puede venir más de un producto separado por comas o saltos de línea
            separadores = [",", "\n", ";"]
            productos_nuevos = [incoming_msg]
            for sep in separadores:
                if sep in incoming_msg:
                    productos_nuevos = [p.strip() for p in incoming_msg.replace("\n", ",").replace(";", ",").split(",")]
                    break

            productos_nuevos = [p for p in productos_nuevos if p]  # filtra vacíos

            fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
            quien = USUARIOS.get(sender, profile_name or "Alguien")
            filas = [[p.capitalize(), quien, fecha] for p in productos_nuevos]
            sheet.append_rows(filas)

            if len(productos_nuevos) == 1:
                msg.body(f"✅ *{productos_nuevos[0].capitalize()}* agregado a la lista!")
                notificar_otro(sender, f"🛒 *{quien}* agregó *{productos_nuevos[0].capitalize()}* a la lista del super.")
            else:
                items = ", ".join(p.capitalize() for p in productos_nuevos)
                msg.body(f"✅ Agregué {len(productos_nuevos)} productos: {items}")
                notificar_otro(sender, f"🛒 *{quien}* agregó {len(productos_nuevos)} productos a la lista: {items}")

    except Exception as e:
        print(f"ERROR: {e}")
        msg.body("❌ Ocurrió un error. Intentá de nuevo en unos segundos.")

    return str(resp)

# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return "Bot Lista Super activo ✅", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
