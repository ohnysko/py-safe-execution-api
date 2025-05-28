FROM python:3.12

RUN apt-get update && apt-get install -y \
    git build-essential clang protobuf-compiler libprotobuf-dev libnl-route-3-dev \
    pkg-config libcap-dev libseccomp-dev flex bison libcap2-bin

# Create necessary directories and symlinks for libraries
RUN mkdir -p /lib64 && \
    ln -s /lib/x86_64-linux-gnu /lib64/x86_64-linux-gnu

RUN git clone https://github.com/google/nsjail.git /opt/nsjail && \
    cd /opt/nsjail && make && cp nsjail /usr/local/bin/nsjail

# Create necessary directories for nsjail
RUN mkdir -p /var/empty && \
    mkdir -p /var/empty/nsjail && \
    chmod 755 /var/empty/nsjail

# Ensure proc is properly mounted and accessible
RUN mkdir -p /proc && \
    chmod 555 /proc

COPY requirements.txt .
RUN pip install -r requirements.txt
    
COPY . /app
WORKDIR /app

RUN chmod 644 /app/config.proto

# Set up proper permissions for nsjail
RUN chmod 755 /usr/local/bin/nsjail && \
    chown root:root /usr/local/bin/nsjail

# Create and set permissions for tmp directory
RUN mkdir -p /tmp && \
    chmod 1777 /tmp

# Create a non-root user
RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

CMD ["python", "app.py"]