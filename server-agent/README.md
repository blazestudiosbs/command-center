# Vera Server Agent

This read-only Linux agent reports uptime, one-minute load, memory, root-disk use, and Docker running/total counts. It cannot receive or execute commands.

Register the server on Command Center's Infrastructure page and copy the one-time token. On the server being monitored:

```bash
sudo install -d -m 0700 /etc/vera
sudo nano /etc/vera/server-agent.env
```

Add:

```dotenv
VERA_COMMAND_CENTER_URL=https://command-center.tail6031ec.ts.net
VERA_SERVER_TOKEN=paste-the-one-time-token
```

Then run from the checked-out repository:

```bash
sudo chmod 600 /etc/vera/server-agent.env
sudo ./server-agent/install.sh
```

The timer reports every two minutes. The token can be disabled or replaced from Command Center.
