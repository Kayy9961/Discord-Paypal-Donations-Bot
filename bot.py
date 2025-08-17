
import os
import re
import json
import asyncio
import imaplib
import email
import traceback
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import discord
from discord import Embed, Colour

load_dotenv()
DISCORD_TOKEN         = os.getenv("DISCORD_TOKEN")
GUILD_ID              = int(os.getenv("GUILD_ID"))
DONATIONS_CHANNEL_ID  = int(os.getenv("DONATIONS_CHANNEL_ID"))
IMAP_SERVER           = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_EMAIL            = os.getenv("IMAP_EMAIL")
IMAP_PASSWORD         = os.getenv("IMAP_PASSWORD")
PAYPAL_SENDERS_RAW    = os.getenv("PAYPAL_SENDERS")
PAYPAL_SENDERS        = [s.strip() for s in PAYPAL_SENDERS_RAW.split(",") if s.strip()]
PAYPAL_ME             = os.getenv("PAYPAL_ME")
POLL_SECONDS          = int(os.getenv("POLL_SECONDS"))
MAX_EMAILS            = int(os.getenv("MAX_EMAILS"))

DATA_FILE             = "donations.json"
SEEN_FILE             = "processed_ids.json"
EMBED_FILE            = "embed_message.json" 

def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def load_totals():
    data = _load_json(DATA_FILE, {})
    clean = {}
    for k, v in data.items():
        try:
            clean[str(k)] = round(float(v), 2)
        except Exception:
            continue
    return clean

def save_totals(data):
    _save_json(DATA_FILE, data)

def load_seen():
    return set(_load_json(SEEN_FILE, []))

def save_seen(seen):
    _save_json(SEEN_FILE, sorted(list(seen)))

def load_embed_info():
    return _load_json(EMBED_FILE, {})

def save_embed_info(info):
    _save_json(EMBED_FILE, info)

def conectar_imap():
    print(f"[IMAP] Conectando a {IMAP_SERVER} como {IMAP_EMAIL}...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(IMAP_EMAIL, IMAP_PASSWORD)
    print("[IMAP] Login correcto ✅")
    typ, _ = mail.select("INBOX")
    if typ != "OK":
        raise RuntimeError("No se pudo seleccionar INBOX")
    return mail

def buscar_correos_sync(mail):
    all_ids = set()
    for sender in PAYPAL_SENDERS:
        typ, data = mail.search(None, 'FROM', f'"{sender}"')
        if typ != 'OK':
            print(f"[IMAP] No se pudieron recuperar los correos para {sender}.")
            continue
        ids = data[0].split()
        print(f"[IMAP]   {len(ids)} correos encontrados de {sender}")
        if not ids:
            continue
        if MAX_EMAILS and MAX_EMAILS > 0:
            ids = ids[-MAX_EMAILS:]
            print(f"[IMAP]   Usando últimos {len(ids)} ids para {sender}")
        all_ids.update(ids)

    out = sorted(all_ids, key=lambda x: int(x))
    print(f"[IMAP] Total ids a revisar: {len(out)}")
    return out

async def buscar_correos_async(mail):
    return await asyncio.to_thread(buscar_correos_sync, mail)

AMOUNT_RE = re.compile(
    r'(?:ha recibido|importe recibido|le ha enviado)[^\d]*([\d.,]+)\s*(?:€|EUR)',
    re.IGNORECASE
)

NOTE_RE = re.compile(
    r'(?:Nota|Mensaje) de .+\n([^\n]+)',
    re.IGNORECASE
)

DISCORD_ID_RE = re.compile(r'\b\d{17,20}\b')

def extraer_datos(cuerpo_html):
    soup = BeautifulSoup(cuerpo_html or "", 'html.parser')
    texto = soup.get_text(separator='\n', strip=True)
    texto_norm = (texto.replace("\xa0", " ")
                        .replace("\u202f", " ")
                        .replace("\u2007", " ")
                        .replace("\u2009", " "))
    print(f"[PARSE][TXT] {texto_norm[:200]}...")

    if re.search(r'\bha enviado un pago\b|\byou sent\b', texto_norm, re.IGNORECASE):
        return None, None, None

    amount = None
    note = None
    did = None

    m_amt = AMOUNT_RE.search(texto_norm)
    if m_amt:
        raw = m_amt.group(1)
        try:
            t = raw
            if "," in t and "." in t:
                if t.rfind(",") > t.rfind("."):
                    t = t.replace(".", "").replace(",", ".")
                else:
                    t = t.replace(",", "")
            else:
                if "," in t and "." not in t:
                    t = t.replace(",", ".")
            val = float(t)
            if 0 < val <= 10000:
                amount = val
        except Exception:
            amount = None

    m_note = NOTE_RE.search(texto_norm)
    if m_note:
        note = m_note.group(1).strip()
        m_did = DISCORD_ID_RE.search(note)
        if m_did:
            did = m_did.group(0)

    return amount, note, did

def get_message_body(msg):
    if msg.is_multipart():
        html_parts = []
        plain_parts = []
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/html":
                payload = part.get_payload(decode=True)
                if payload is not None:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html_parts.append(payload.decode(charset, errors="replace"))
                    except Exception:
                        html_parts.append(payload.decode("utf-8", errors="replace"))
            elif ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if payload is not None:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        plain_parts.append(payload.decode(charset, errors="replace"))
                    except Exception:
                        plain_parts.append(payload.decode("utf-8", errors="replace"))
        if html_parts:
            return "\n".join(html_parts)
        if plain_parts:
            return "\n".join(plain_parts)
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload is None:
            raw = msg.get_payload(decode=False)
            return raw if isinstance(raw, str) else ""
        charset = msg.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except Exception:
            return payload.decode("utf-8", errors="replace")

def _fmt_user(guild: discord.Guild, did_str: str) -> str:
    try:
        did_int = int(did_str)
    except Exception:
        return f"<@{did_str}>"
    member = guild.get_member(did_int)
    return member.mention if member else f"<@{did_str}>"

def build_leaderboard_embed(guild: discord.Guild, totals: dict[str, float]):
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    title = "💙 Donaciones"
    description = (
        f"Gracias por apoyar el proyecto de KayyShop, estos fondos serán utilizados para inversiones en el servidores y mejorar la calidad.\n\n"
        f"➡️ Para donar: **{PAYPAL_ME}**\n"
        f"✍️ Pon tu **ID de Discord** en la *nota* del pago (p. ej. `399876603229896704`)."
    )
    embed = Embed(title=title, description=description, colour=Colour.blue())

    if not ranked:
        embed.add_field(
            name="Aún no hay donaciones",
            value="Sé el primero en aparecer aquí 🎉",
            inline=False
        )
    else:
        medals = ["🥇", "🥈", "🥉"]
        for i, (did, amt) in enumerate(ranked[:3]):
            place = f"{medals[i]}  Top {i+1}"
            mention = _fmt_user(guild, did)
            embed.add_field(
                name=place,
                value=f"{mention} — **{amt:.2f} €**",
                inline=False
            )

        # Resto
        if len(ranked) > 3:
            lines = []
            for pos, (did, amt) in enumerate(ranked[3:], start=4):
                lines.append(f"`#{pos:02d}` {_fmt_user(guild, did)} — **{amt:.2f} €**")
            embed.add_field(name="Otros donantes", value="\n".join(lines[:15]), inline=False)

    total_recaudado = sum(v for v in totals.values() if isinstance(v, (int, float)))
    embed.add_field(
        name="💰 Total recaudado",
        value=f"**{total_recaudado:.2f} €**",
        inline=False
    )

    proxima = datetime.now() + timedelta(seconds=max(1, POLL_SECONDS))
    embed.set_footer(text=f"Gracias a todos los que apoyan el servidor de KayyShop ♥️")
    return embed

intents = discord.Intents.none()
intents.guilds = True
client = discord.Client(intents=intents)

async def resolve_channel_or_fail():
    guild = client.get_guild(GUILD_ID) if GUILD_ID else None
    if guild:
        ch = guild.get_channel(DONATIONS_CHANNEL_ID)
        if ch:
            return ch
    ch = client.get_channel(DONATIONS_CHANNEL_ID)
    if ch:
        return ch
    try:
        return await client.fetch_channel(DONATIONS_CHANNEL_ID)
    except Exception as e:
        print("[DISCORD] Error al resolver canal:", e)
        traceback.print_exc()
        raise

async def ensure_embed_message(channel: discord.TextChannel):
    if channel is None:
        raise RuntimeError("Canal no resuelto (None) al crear/editar el embed).")

    info = load_embed_info()
    msg_id = info.get("message_id")

    if msg_id:
        try:
            msg = await channel.fetch_message(int(msg_id))
            print(f"[BOT] Reutilizando embed existente (message_id={msg.id})")
            return msg
        except Exception as e:
            print(f"[BOT] No se pudo reutilizar message_id={msg_id}. Se creará uno nuevo. Motivo: {e}")

    totals = load_totals()
    embed = build_leaderboard_embed(channel.guild, totals)
    try:
        msg = await channel.send(embed=embed)
        print(f"[BOT] Embed creado ✅ (message_id={msg.id})")
        save_embed_info({"channel_id": channel.id, "message_id": msg.id})
        try:
            await msg.pin()
            print("[BOT] Embed fijado (pin) ✅")
        except Exception as e:
            print(f"[BOT] No se pudo fijar el embed (pin): {e}")
        return msg
    except Exception as e:
        print(f"[BOT] ERROR al enviar embed: {e}")
        traceback.print_exc()
        raise

async def update_embed(channel: discord.TextChannel):
    msg = await ensure_embed_message(channel)
    totals = load_totals()
    embed = build_leaderboard_embed(channel.guild, totals)
    try:
        await msg.edit(embed=embed)
        total_recaudado = sum(v for v in totals.values() if isinstance(v, (int, float)))
        print(f"[BOT] Embed editado ✅ (message_id={msg.id}) | Donantes: {len(totals)} | Total: {total_recaudado:.2f} €")
    except Exception as e:
        print("Error al editar embed:", e)
        traceback.print_exc()
        raise

async def poll_once_and_update(channel: discord.TextChannel):
    seen = load_seen()
    totals = load_totals()
    new_seen = False

    mail = None
    try:
        mail = await asyncio.to_thread(conectar_imap)
        ids = await buscar_correos_async(mail)

        for num in ids:
            seq_id = num.decode() if isinstance(num, (bytes, bytearray)) else str(num)
            if seq_id in seen:
                continue

            typ, data = await asyncio.to_thread(mail.fetch, num, '(RFC822)')
            if typ != 'OK' or not data or not isinstance(data[0], tuple):
                print(f"[IMAP] fetch falló para id={seq_id}")
                continue

            msg = email.message_from_bytes(data[0][1])
            cuerpo = get_message_body(msg)

            amount, note, did = extraer_datos(cuerpo)
            print(f"[MAIL] id={seq_id} | amount={amount} | note={note} | did={did}")

            seen.add(seq_id)
            new_seen = True
            if amount is None or not did:
                print("[MAIL] Ignorado (sin ID o sin importe)")
                continue

            prev = totals.get(did, 0.0)
            try:
                prev = float(prev)
            except Exception:
                prev = 0.0
            totals[did] = round(prev + float(amount), 2)
            print(f"[DONACIÓN] {did} ahora tiene {totals[did]:.2f} €")

    except Exception as e:
        print("[ERROR] En poll_once_and_update:", e)
        traceback.print_exc()
    finally:
        if mail:
            try:
                mail.logout()
                print("[IMAP] Sesión cerrada")
            except:
                pass

    if new_seen:
        save_seen(seen)
        save_totals(totals)
        await update_embed(channel)
        print("[BOT] Embed actualizado tras nuevas donaciones ✅")
    else:
        print("[BOT] No hay correos nuevos no procesados")

async def poll_loop():
    await client.wait_until_ready()
    if not client.is_ready():
        return

    try:
        channel = await resolve_channel_or_fail()
        print(f"[DISCORD] Canal resuelto: #{channel.name} (id={channel.id})")
    except Exception:
        print("[DISCORD] No se pudo resolver canal")
        return

    perms = channel.permissions_for(channel.guild.me)
    needed = []
    if not perms.view_channel:   needed.append("Ver canal")
    if not perms.send_messages:  needed.append("Enviar mensajes")
    if not perms.embed_links:    needed.append("Insertar enlaces/embeds")
    if needed:
        print("[DISCORD] Faltan permisos en el canal:", ", ".join(needed))
        return

    await ensure_embed_message(channel)
    await update_embed(channel)

    while not client.is_closed():
        await poll_once_and_update(channel)
        await asyncio.sleep(max(30, POLL_SECONDS))

@client.event
async def on_ready():
    print(f"[DISCORD] Conectado como {client.user} (id={client.user.id})")
    client.loop.create_task(poll_loop())

if __name__ == "__main__":
    missing = [k for k, v in {
        "DISCORD_TOKEN": DISCORD_TOKEN,
        "GUILD_ID": GUILD_ID,
        "DONATIONS_CHANNEL_ID": DONATIONS_CHANNEL_ID,
        "IMAP_SERVER": IMAP_SERVER,
        "IMAP_EMAIL": IMAP_EMAIL,
        "IMAP_PASSWORD": IMAP_PASSWORD,
    }.items() if not v]
    if missing:
        raise SystemExit(f"Faltan variables en .env: {', '.join(missing)}")

    try:
        client.run(DISCORD_TOKEN)
    except Exception as e:
        print("[FATAL] No se pudo iniciar el bot:", e)
        traceback.print_exc()
