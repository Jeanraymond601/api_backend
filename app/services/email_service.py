# app/services/email_service.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# ✅ Charger les variables d'environnement depuis .env
load_dotenv()

class EmailService:
    def __init__(self):
        # Configuration SMTP depuis .env
        self.smtp_server = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.sender_email = os.getenv('SMTP_USERNAME', '')
        self.sender_password = os.getenv('SMTP_PASSWORD', '')
        self.sender_name = os.getenv('FROM_NAME', 'Live Commerce')
        self.from_email = os.getenv('FROM_EMAIL', self.sender_email)
        
        print(f"📧 Configuration SMTP chargée:")
        print(f"   Serveur: {self.smtp_server}:{self.smtp_port}")
        print(f"   Utilisateur: {self.sender_email}")
        print(f"   Expéditeur: {self.sender_name} <{self.from_email}>")
        
        # Vérifier la configuration
        if not self.sender_email or not self.sender_password:
            print("⚠️ ERREUR: Configuration SMTP incomplète dans .env")
            print("💡 Vérifiez que SMTP_USERNAME et SMTP_PASSWORD sont définis")
        else:
            print("✅ Configuration SMTP OK")
    
    def send_email(self, to_email: str, subject: str, html_content: str, text_content: str = "") -> bool:
        """
        Envoie un email générique via SMTP avec contenu HTML et texte
        """
        try:
            print(f"📧 Tentative d'envoi SMTP à: {to_email}")
            print(f"   Sujet: {subject}")
            
            # Créer le message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.sender_name} <{self.from_email}>"
            message["To"] = to_email
            
            # Si pas de contenu texte, générer depuis HTML
            if not text_content:
                import re
                # Simple conversion HTML -> texte
                text_content = re.sub('<[^<]+?>', '', html_content)
                text_content = text_content.replace('&nbsp;', ' ').strip()
            
            # Convertir en MIMEText
            part1 = MIMEText(text_content, "plain", "utf-8")
            part2 = MIMEText(html_content, "html", "utf-8")
            
            # Ajouter les parties au message
            message.attach(part1)
            message.attach(part2)
            
            # Connexion et envoi
            print(f"🔗 Connexion à {self.smtp_server}:{self.smtp_port}...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                server.ehlo()
                
                # Démarrer TLS (obligatoire pour Gmail)
                print("🔐 Démarrage TLS...")
                server.starttls()
                server.ehlo()
                
                # Authentification
                print(f"🔑 Authentification en tant que {self.sender_email}...")
                server.login(self.sender_email, self.sender_password)
                
                # Envoi de l'email
                print("📤 Envoi de l'email...")
                server.sendmail(self.from_email, to_email, message.as_string())
                
                print(f"✅ Email envoyé avec succès à: {to_email}")
                return True
                
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ ERREUR d'authentification SMTP: {e}")
            print("💡 Pour Gmail, assurez-vous que:")
            print("   1. Vous utilisez un mot de passe d'application (pas votre mot de passe normal)")
            print("   2. L'authentification 2 facteurs est activée sur votre compte Google")
            print("   3. Les apps moins sécurisées sont autorisées si vous n'avez pas 2FA")
            return False
            
        except smtplib.SMTPException as e:
            print(f"❌ ERREUR SMTP: {e}")
            return False
            
        except Exception as e:
            print(f"❌ ERREUR générale d'envoi d'email: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def send_reset_code_email(self, recipient_email: str, reset_code: str) -> bool:
        """
        Envoie un email avec le code de réinitialisation via SMTP
        """
        try:
            subject = "Code de réinitialisation - Live Commerce"
            html_content = self._generate_html_template(reset_code)
            text_content = self._generate_text_template(reset_code)
            
            return self.send_email(recipient_email, subject, html_content, text_content)
                
        except Exception as e:
            print(f"❌ ERREUR lors de l'envoi d'email de réinitialisation: {str(e)}")
            return False
    
    def test_connection(self) -> bool:
        """Teste la connexion SMTP"""
        try:
            print(f"🔍 Test de connexion SMTP à {self.smtp_server}:{self.smtp_port}")
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.ehlo()
                
                # Démarrer TLS
                server.starttls()
                server.ehlo()
                
                # Essayer de se connecter
                if self.sender_email and self.sender_password:
                    server.login(self.sender_email, self.sender_password)
                
                print("✅ Connexion SMTP réussie")
                return True
                
        except Exception as e:
            print(f"❌ ERREUR test connexion SMTP: {str(e)}")
            return False

    def _generate_html_template(self, reset_code: str) -> str:
        """Génère le template HTML basé sur le design fourni"""
        return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Code de réinitialisation - Live Commerce</title>
</head>
<body style="font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        
        <!-- Header -->
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #4F46E5; margin: 0;">🛍️ Live Commerce</h1>
            <p style="color: #666; margin-top: 5px;">Votre marketplace de confiance</p>
        </div>
        
        <!-- Icon -->
        <div style="text-align: center; margin: 30px 0;">
            <div style="font-size: 60px; color: #4F46E5;">🔐</div>
        </div>
        
        <!-- Title -->
        <h2 style="color: #333; text-align: center; margin-bottom: 10px;">
            Code de réinitialisation
        </h2>
        
        <p style="color: #666; text-align: center; margin-bottom: 30px;">
            Utilisez le code ci-dessous pour réinitialiser votre mot de passe.
        </p>
        
        <!-- Code Box -->
        <div style="text-align: center; margin: 40px 0;">
            <div style="display: inline-block; background: linear-gradient(135deg, #4F46E5, #7C3AED); 
                        color: white; font-size: 32px; font-weight: bold; padding: 20px 40px; 
                        border-radius: 10px; letter-spacing: 10px; font-family: monospace;">
                {reset_code}
            </div>
        </div>
        
        <!-- Instructions -->
        <div style="background-color: #F3F4F6; padding: 20px; border-radius: 8px; margin: 30px 0;">
            <p style="color: #374151; margin: 0 0 10px 0;">
                <strong>Instructions :</strong>
            </p>
            <ul style="color: #6B7280; margin: 0; padding-left: 20px;">
                <li>Copiez ce code de 6 chiffres</li>
                <li>Retournez sur la page de réinitialisation</li>
                <li>Collez le code dans le champ prévu</li>
                <li>Créez votre nouveau mot de passe</li>
            </ul>
        </div>
        
        <!-- Warning -->
        <div style="background-color: #FEF3C7; border-left: 4px solid #D97706; 
                    padding: 15px; margin: 20px 0; border-radius: 4px;">
            <p style="color: #92400E; margin: 0;">
                <strong>⚠️ Important :</strong> Ce code expire dans 15 minutes.<br>
                <strong>🔒 Sécurité :</strong> Ne partagez jamais ce code avec qui que ce soit.
            </p>
        </div>
        
        <!-- Footer -->
        <div style="border-top: 1px solid #E5E7EB; margin-top: 40px; padding-top: 20px; text-align: center;">
            <p style="color: #9CA3AF; font-size: 14px; margin: 0 0 10px 0;">
                Si vous n'avez pas demandé cette réinitialisation, ignorez simplement cet email.
            </p>
            <p style="color: #6B7280; font-size: 12px; margin: 0;">
                © 2024 Live Commerce. Tous droits réservés.<br>
                <a href="mailto:{self.from_email}" style="color: #4F46E5; text-decoration: none;">
                    {self.from_email}
                </a>
            </p>
        </div>
        
    </div>
</body>
</html>
"""
    
    def _generate_text_template(self, reset_code: str) -> str:
        """Génère la version texte"""
        return f"""LIVE COMMERCE - RÉINITIALISATION DE MOT DE PASSE

Bonjour,

Vous avez demandé la réinitialisation de votre mot de passe sur Live Commerce.

VOTRE CODE DE VÉRIFICATION :
{reset_code}

Instructions :
1. Copiez ce code de 6 chiffres
2. Retournez sur la page de réinitialisation
3. Collez le code dans le champ prévu
4. Créez votre nouveau mot de passe

⚠️ IMPORTANT :
• Ce code expire dans 15 minutes
• Ne partagez jamais ce code avec qui que ce soit
• Si vous n'avez pas fait cette demande, ignorez cet email

Besoin d'aide ? Contactez-nous à : {self.from_email}

--
Live Commerce
Votre marketplace de confiance
© 2024 Live Commerce. Tous droits réservés.
"""

# Instance globale
email_service = EmailService()