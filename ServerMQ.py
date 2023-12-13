import stomp
import urllib3
import urllib3.util
import Pyro4
import Pyro4.naming
from random import choices
import string
import threading
import json
import sys

clients = {}
topics = {}

def threaded(func):
    def wrapper(*args, **kwargs):
        return threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True).start()
    return wrapper

def id_generator(size):
    return ''.join(choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=size))

http = urllib3.PoolManager()
headers = urllib3.make_headers(basic_auth='admin:admin')

def load_server_data():
    global clients, topics
    addresses = http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/listAddresses(java.lang.String)/,', headers=headers).json()
    addresses = addresses['value'].split(',')
    for address in addresses:
        if address in ['DLQ', 'ExpiryQueue', 'activemq.notifications', '$sys.mqtt.sessions']:
            continue
        address_info = http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/getAddressInfo/{address}', headers=headers).json()
        address_info = address_info['value']
        if 'ANYCAST' in address_info:
            clients[address] = None
        else:
            topics[address] = []
            response = http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/getQueueNames/MULTICAST', headers=headers).json()
            topic_names = response['value']
            for topic in topic_names:
                topic = topic.split('.')
                topic_name = topic[0]
                if topic_name == address:
                    topics[address].append(topic[1])
            
@threaded
def start_ns():
    print('Inicializando o servidor de nomes...')
    Pyro4.naming.startNSloop(host='localhost', port=9090)

class Listener(stomp.ConnectionListener):
    def on_error(self, frame):
        print(f'[ERROR] {frame.headers["error"]}')
    
    def on_message(self, frame):
        origin = frame.headers['name']
        destination = frame.headers['target']
        type = frame.headers['type']
        if type == 'topic':
            topic = frame.headers['topic']
            clients[destination].redirect_message(frame.body, origin, topic)
        elif type == 'contact':
            clients[destination].redirect_message(frame.body, origin)
        elif type == 'new contact':
            clients[destination].message_popup(f'{origin} o adicionou como contato!')

class Client:

    @Pyro4.expose
    def start(self, name, uri):
        if name in clients.keys():
            if clients[name] != None:
                return False
        else:
            print(f'Criando nova conta para cliente {name}...')
            q_json = json.dumps({"name": name, "address": name, "routing-type": "ANYCAST", "durable": True})
            http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/createQueue(java.lang.String)/{q_json}', headers=headers).json()
        self.name = name
        self.id = id_generator(10)
        self.client = Pyro4.Proxy(uri)
        clients[self.name] = self.client
        print(f'Cliente {self.name} se logou!')
        self.load_client_contacts()
        return True
        
    @Pyro4.expose
    def notificationQueue(self):
        conn.subscribe(self.name, id=self.name, headers={'subscription-type': 'ANYCAST', 'durable-subscription-name': self.name})

    @Pyro4.expose
    @property
    def get_clients(self):
        return clients
    
    @Pyro4.expose
    @property
    def get_topics(self):
        return topics

    def load_client_contacts(self):
        response = http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/getQueueNames/ANYCAST', headers=headers).json()
        client_queues = response['value']
        for queue in client_queues:
            queue = queue.split('.')
            try:
                if queue[0] == self.name:
                    client_name = queue[1]
                    if client_name in clients.keys():
                        self.client.load_contact(client_name, 'client')
                        p_mens = http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0",component=addresses,address="{self.name}",subcomponent=queues,routing-type="anycast",queue="{self.name}.{client_name}"/countMessages()', headers=headers).json()
                        p_mens = p_mens['value']
                        self.client.notify(p_mens, client_name)
            except:
                continue
        for topic in topics.keys():
            if self.name in topics[topic]:
                self.client.load_contact(topic, 'topic')
                p_mens = http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0",component=addresses,address="{topic}",subcomponent=queues,routing-type="multicast",queue="{topic}.{self.name}"/countMessages()', headers=headers).json()
                p_mens = p_mens['value']
                self.client.notify(p_mens, topic)

    @Pyro4.expose
    def open_connection(self, target):
        if target in topics.keys():
            conn.subscribe(f'{target}::{target}.{self.name}', id=f'{target}.{self.name}', headers={'subscription-type': 'MULTICAST', 'durable-subscription-name': self.name})
        else:
            conn.subscribe(f'{self.name}::{self.name}.{target}', id=f'{self.name}.{target}', headers={'subscription-type': 'ANYCAST', 'durable-subscription-name': self.name})

    @Pyro4.expose
    def close_connection(self, target):
        if target in topics.keys():
            conn.unsubscribe(f'{target}.{self.name}')
        else:
            conn.unsubscribe(f'{self.name}.{target}')

    @Pyro4.expose
    def removeQueue(self, name, type):
        global topics
        if type == 'contact':
            http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/destroyQueue(java.lang.String)/{self.name}.{name}', headers=headers).json()
        elif type == 'topic':
            http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/destroyQueue(java.lang.String)/{name}.{self.name}', headers=headers).json()
            topics[name].remove(self.name)
            if topics[name] == []:
                http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/deleteAddress(java.lang.String,boolean)/{name}/true', headers=headers).json()
                print(f'Tópico {name} foi deletado por não conter membros!')

    @Pyro4.expose
    def new_contact(self, name):
        if name in clients.keys():
            try:
                clients[name].load_contact(self.name, 'client')
                clients[name].message_popup(f'{self.name} o adicionou como contato!')
            except:
                conn.send(name, self.name, headers={'persistent': True, 'name': self.name, 'target': name, 'type': 'new contact'})
            q_json = json.dumps({"name": f"{self.name}.{name}", "address": self.name, "routing-type": "ANYCAST", "durable": True})
            http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/createQueue(java.lang.String)/{q_json}', headers=headers).json()
            q_json = json.dumps({"name": f"{name}.{self.name}", "address": name, "routing-type": "ANYCAST", "durable": True})
            http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/createQueue(java.lang.String)/{q_json}', headers=headers).json()
            return True
        else:
            return False
        
    @Pyro4.expose
    def new_topic(self, name):
        global topics
        q_json = json.dumps({"name": f"{name}.{self.name}", "address": name, "routing-type": "MULTICAST", "durable": True})
        http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/createQueue(java.lang.String)/{q_json}', headers=headers).json()
        if name not in topics.keys():
            topics[name] = []
        topics[name].append(self.name)

    @Pyro4.expose
    def send_message(self, msg, target, type):
        if type == 'contact':
            request = http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0",component=addresses,address="{target}",subcomponent=queues,routing-type="multicast",queue="{target}.{self.name}"/browse()', headers=headers).json()
            if request['status'] != 200:
                q_json = json.dumps({"name": f"{target}.{self.name}", "address": target, "routing-type": "ANYCAST", "durable": True})
                http.request('GET', f'http://localhost:8161/console/jolokia/exec/org.apache.activemq.artemis:broker="0.0.0.0"/createQueue(java.lang.String)/{q_json}', headers=headers).json()
            conn.send(f'{target}::{target}.{self.name}', msg, headers={'persistent': True, 'name': self.name, 'target': target, 'type': type})
            try:
                clients[target].notify(1, self.name)
            except:
                pass
        elif type == 'topic':
            for client in topics[target]:
                conn.send(f'{target}::{target}.{client}', msg, headers={'persistent': True, 'name': self.name, 'target': client, 'type': type, 'topic': target})
                try:
                    clients[client].notify(1, target)
                except:
                    pass

    @Pyro4.expose
    def logout(self):
        conn.unsubscribe(self.name)
        clients[self.name] = None
        print(f'Cliente {self.name} se desconectou!')

try:
    conn = stomp.Connection([('localhost', 61613)], auto_content_length=False, heartbeats=(4000, 4000))
except:
    input('[ERROR] Broker não iniciado!')
    sys.exit()
conn.set_listener('', Listener())
conn.connect('admin', 'admin', wait=True, headers={'client-id': 'admin'})

start_ns()
daemon = Pyro4.Daemon(host='localhost', port=8080)
uri = daemon.register(Client)
ns = Pyro4.locateNS()
ns.register('Server', uri)
load_server_data()
print('Servidor inicializado!')
print(f'clientes: {clients}')
print(f'tópicos: {topics}')
daemon.requestLoop()