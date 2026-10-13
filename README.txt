LAN Audio Pipe
==============
PC 1 (sender) streams whatever is playing on its speakers to PC 2 (receiver),
which plays it on its default speaker. Uncompressed PCM over UDP, port 50007.

Requirements
------------
- Both PCs on the same local network. Wired is best.
- Running from source: Python 3.11+ and  pip install PyAudioWPatch
- Running the .exe builds: nothing else needed.

Usage
-----
1. On PC 2 (receiver), find its IP: run  ipconfig  and note the
   "IPv4 Address" (e.g. 192.168.1.42).

2. On PC 2 start the receiver:
       receiver.exe                      (or: python receiver.py)
   Options:  --port 50007  --buffer-ms 40

3. On PC 1 start the sender with PC 2's IP:
       sender.exe 192.168.1.42           (or: python sender.py 192.168.1.42)
   Options:  --port 50007

4. Play something on PC 1. Ctrl+C stops either side; the other side keeps
   running. Restart the sender any time and audio resumes on its own.

Firewall
--------
On first run, Windows Firewall will prompt on the receiver. Allow it on
Private networks. If you missed the prompt (or your network is set to Public),
allow inbound UDP 50007 manually, e.g. from an admin prompt:
    netsh advfirewall firewall add rule name="LAN Audio Pipe" dir=in action=allow protocol=UDP localport=50007

Tips
----
- On Wi-Fi, if audio crackles or drops out, raise the buffer:
      receiver.exe --buffer-ms 80        (try 60-100)
  More buffer = more delay, fewer glitches.
- Nothing is sent while PC 1 is silent. That's normal; the receiver plays
  silence until audio comes back.
- The sender captures the *default* output device at the moment it starts.
  If you switch speakers/headphones on PC 1, restart the sender.
- If PC 2's speaker uses a different sample rate or channel count, the receiver
  converts automatically (it prints "converting").

Building the .exe files
-----------------------
    pip install pyinstaller
    pyinstaller --onefile sender.py
    pyinstaller --onefile receiver.py
The executables end up in dist\. Copy sender.exe to PC 1 and receiver.exe to PC 2.
