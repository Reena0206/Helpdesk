import smtplib

try:
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login('iamreena06@gmail.com', 'ismz cnab jhmm dlih')
    print("SMTP connection successful!")
    server.quit()
except Exception as e:
    print(f"Error: {e}")