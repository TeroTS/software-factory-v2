# Configure container account/home/socket groups from UID/GID arguments; propagate errors and never touch the workspace.
import os
import sys
import time
import uuid
from pathlib import Path

uid, gid = map(int, sys.argv[1:])
home = Path("/tmp/factory-home")
home.mkdir(mode=0o700)
os.chown(home, uid, gid)
passwd = Path("/etc/passwd")
users = [line.split(":") for line in passwd.read_text().splitlines()]
user = next((entry for entry in users if int(entry[2]) == uid), None)
if user is None:
    user = ["f" + uuid.uuid4().hex[:16], "x", str(uid), str(gid), "", str(home), "/bin/sh"]
    users.append(user)
user[3], user[5] = str(gid), str(home)
passwd.write_text("".join(":".join(entry) + "\n" for entry in users))
shadow = Path("/etc/shadow")
if not any(line.split(":")[0] == user[0] for line in shadow.read_text().splitlines()):
    with shadow.open("a") as stream:
        stream.write(f"{user[0]}:!:{int(time.time() // 86400)}:0:99999:7:::\n")
group = Path("/etc/group")
groups = [line.split(":") for line in group.read_text().splitlines()]
socket = Path("/var/run/docker.sock")
gids = {gid}
if socket.exists():
    gids.add(socket.stat().st_gid)
for number in gids:
    entry = next((entry for entry in groups if int(entry[2]) == number), None)
    if entry is None:
        entry = ["f" + uuid.uuid4().hex[:16], "x", str(number), ""]
        groups.append(entry)
    members = set(filter(None, entry[3].split(",")))
    members.add(user[0])
    entry[3] = ",".join(sorted(members))
group.write_text("".join(":".join(entry) + "\n" for entry in groups))
