# Start from a standard Ubuntu (Linux) image
FROM ubuntu:22.04

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run the system installer (apt-get) to install Python, Pip, and TESSERACT
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    tesseract-ocr \
    libtesseract-dev \
    && apt-get clean

# Upgrade pip
RUN pip3 install --upgrade pip

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file *first* (for better build caching)
COPY requirements.txt .

# Install all Python packages from your requirements file
RUN pip3 install -r requirements.txt

# Install the spaCy model
RUN python3 -m spacy download en_core_web_sm

# Copy the rest of your backend code (like process_marksheet.py)
COPY . .

# Tell Render what command to run to start your server
# We use gunicorn, which is in your requirements.txt
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "process_marksheet:app"]
