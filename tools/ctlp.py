import sys, time, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
CTL = ROOT/"work/ctl_park.txt"
def send(l):
    with open(CTL,"a") as f: f.write(l+"\n")
cmd=sys.argv[1]
if cmd=="key":
    send(sys.argv[2]); print(">",sys.argv[2])
elif cmd=="shot":
    send("shot "+str(ROOT/"work/shots"/sys.argv[2])); print("shot",sys.argv[2])
