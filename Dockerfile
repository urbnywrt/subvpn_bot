FROM python:3.11

WORKDIR /app

COPY . .
RUN apt-get update && apt-get install nano git -y
RUN pip install -r requirements.txt
RUN git clone https://github.com/mewhrzad/marzpy.git /app/marzpy
RUN mv /app/marzpy/marzpy/api/user.py /usr/local/lib/python3.11/site-packages/marzpy/api/user.py

CMD ["python", "bot.py"]
