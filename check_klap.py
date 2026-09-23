import requests
from pytapo import Tapo

t = Tapo("192.168.1.109", "homeadmin", "admin@123")
print("isKLAP:", t.isKLAP)
