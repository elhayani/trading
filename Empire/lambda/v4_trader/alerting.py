"""
Alerting System - Email/Telegram notifications
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd

logger = logging.getLogger(__name__)

class AlertManager:
    def __init__(self, email_config=None, telegram_config=None):
        self.email_config = email_config or {}
        self.telegram_config = telegram_config or {}
    
    def send_alert(self, level: str, title: str, message: str):
        """
        Send alert via configured channels.
        level: 'INFO', 'WARNING', 'CRITICAL'
        """
        logger.log(
            logging.WARNING if level == 'WARNING' else logging.ERROR,
            f"🚨 ALERT [{level}] {title}: {message}"
        )
        
        if self.email_config.get('enabled'):
            self._send_email(level, title, message)
        
        if self.telegram_config.get('enabled'):
            self._send_telegram(level, title, message)
    
    def _send_email(self, level, title, message):
        """Send via Gmail SMTP"""
        try:
            smtp_server = self.email_config.get('smtp_server', 'smtp.gmail.com')
            port = self.email_config.get('port', 587)
            sender = self.email_config['from_email']
            password = self.email_config['password']
            recipient = self.email_config['to_email']
            
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = recipient
            msg['Subject'] = f"[{level}] Empire Trading Bot - {title}"
            
            body = f"""
Empire Trading Bot Alert

Level: {level}
Title: {title}

Message:
{message}

Timestamp: {pd.Timestamp.now()}
"""
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(smtp_server, port) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)
                logger.info(f"✅ Email alert sent to {recipient}")
        except Exception as e:
            logger.error(f"❌ Email alert failed: {e}")
    
    def _send_telegram(self, level, title, message):
        """Send via Telegram Bot API"""
        try:
            import requests
            token = self.telegram_config['bot_token']
            chat_id = self.telegram_config['chat_id']
            
            emoji = {
                'INFO': 'ℹ️',
                'WARNING': '⚠️',
                'CRITICAL': '🚨'
            }.get(level, '📢')
            
            text = f"{emoji} *{title}*\n\n{message}"
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'Markdown'
            })
            
            logger.info(f"✅ Telegram alert sent")
        except Exception as e:
            logger.error(f"❌ Telegram alert failed: {e}")
