from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

folder = Path(__file__).resolve().parent
image = Image.new('RGBA', (256, 256))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((4, 4, 252, 252), radius=56, fill='#6c5ce7')
draw.rounded_rectangle((57, 38, 199, 220), radius=15, fill='white')
draw.polygon([(159,38),(199,78),(159,78)], fill='#dcd6ff')
draw.line([(82,101),(174,101)], fill='#e6e2fa', width=9)
draw.line([(82,119),(155,119)], fill='#e6e2fa', width=9)
font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 91)
draw.text((78,123), 'W', font=font, fill='#6c5ce7')
image.save(folder / 'app.png')
image.save(folder / 'app.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
