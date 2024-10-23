FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt
RUN git clone https://github.com/mewhrzad/marzpy.git
COPY marzpy/marzpy/api/user.py /usr/local/lib/python3.11/site-packages/marzpy/api/user.py

CMD ["python", "bot.py"]
