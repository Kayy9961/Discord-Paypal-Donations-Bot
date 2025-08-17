# 💸 Discord PayPal Donations Bot

Un bot de Discord que conecta tu cuenta de PayPal (vía **IMAP**) con tu servidor para mostrar un **ranking de donaciones** en un canal dedicado.  
Permite reconocer a los donantes con su **ID de Discord** y suma automáticamente sus aportaciones.  

---

## ✨ Características
- 📩 Lee los correos de PayPal mediante IMAP.
- 🔍 Extrae **importe donado** y **nota con ID de Discord**.
- 🏆 Muestra un **ranking de donantes** en un embed en Discord.
- 🔄 Actualización automática cada X minutos.
- 📊 Contador total de dinero recaudado.
- 🛑 Ignora pagos que no incluyan un ID de Discord en la nota.

---

## 📦 Requisitos
- Python 3.9+  
- Librerías:
  - `discord.py`
  - `imaplib`
  - `beautifulsoup4`
  - `asyncio`

---

## ⚙️ Configuración
1. Clona el repositorio:
   ```bash
   git clone https://github.com/Kayy9961/discord-paypal-donations-bot.git
   cd discord-paypal-donations-bot
   ```

2. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. Configura tus credenciales en `config.json` o variables de entorno:
   ```json
   {
     "DISCORD_TOKEN": "tu_token_discord",
     "GUILD_ID": "id_de_tu_servidor",
     "DONATIONS_CHANNEL_ID": "id_del_canal_de_donaciones",
     "IMAP_SERVER": "imap.gmail.com",
     "EMAIL_ACCOUNT": "tu_email@gmail.com",
     "EMAIL_PASSWORD": "tu_contraseña_o_app_password"
   }
   ```

4. Ejecuta el bot:
   ```bash
   python bot.py
   ```

---

## 📝 Notas
- Asegúrate de tener habilitado el acceso IMAP en tu correo.  
- Con Gmail necesitas crear una **contraseña de aplicación** en lugar de tu contraseña normal.  
- Recuerda que los donantes deben poner su **ID de Discord** en la nota del pago para ser reconocidos.  

---

## ❤️ Créditos
Proyecto creado por [Kayy](https://github.com/Kayy9961) para la comunidad.  
Inspirado en la necesidad de apoyar servidores con donaciones transparentes.
