import Pyro4
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
from time import sleep
from sys import exit

Pyro4.config.SERIALIZERS_ACCEPTED = {'serpent', 'marshal'}
daemon = Pyro4.Daemon()
server = None

def threaded(func):
    def wrapper(*args, **kwargs):
        return threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True).start()
    return wrapper

@threaded
def listen2server():
    daemon.requestLoop()

class Topic(tk.Toplevel):
    def __init__(self, master, name):
        self.master = master
        self.name = name
        self.open = False
        self.pendent_messages = 0

    def open_topic(self):
        if self.open:
            return
        else:
            self.open = True
        
        super().__init__(self.master, height=400, width=400)

        top_frame = tk.Frame(self, height=50)
        top_frame.pack(fill='x')

        tk.Label(top_frame, text=f'Tópico {self.name}').pack(side='left', padx=20, pady=10)
        tk.Button(top_frame, text='Listar membros', command=self.list_members).pack(side='right', padx=20, pady=10)

        text_frame = tk.Frame(self, height=350)
        text_frame.pack(fill='x')

        self.textBox = ScrolledText(text_frame, wrap=tk.WORD, state='disabled')
        self.textBox.config(height=20, width=50)
        self.textBox.pack(padx=10, pady=10)

        tk.Label(text_frame, text='Send a message:').pack(padx=5)
        self.entry = tk.Entry(text_frame, width=50)
        self.entry.pack(padx=5, pady=5)
        self.entry.bind('<Return>', lambda e: self.send_message())
        self.entry.focus()

        server.open_connection(self.name)
        self.pendent_messages = 0
        self.protocol('WM_DELETE_WINDOW', self.close_window)

    def list_members(self):
        window = tk.Toplevel(self.master)
        members = server.get_topics[self.name]
        if len(members) < 2:
            tk.Label(window, text='Você é o único membro!').pack(padx=10, pady=10)
            return
        counter = 0
        for member in members:
            if member != client.name:
                tk.Label(window, text=f'{member}').grid(row=counter, column=0, padx=5, pady=5)
                tk.Button(window, text='Adicionar contato', command=lambda: client.add_contact(member, 'client')).grid(row=counter, column=1)
                counter+=1

    def send_message(self, event = None):
        msg = self.entry.get()
        if msg:
            self.entry.delete(0, tk.END)
            server.send_message(msg, self.name, 'topic')

    def message(self, msg):
        self.textBox.config(state='normal')
        self.textBox.insert(tk.END, msg + '\n')
        self.textBox.see('end')
        self.textBox.config(state='disabled')

    def close_window(self):
        server.close_connection(self.name)
        self.open = False
        self.destroy()
        client.update()

class Contact(tk.Toplevel):
    def __init__(self, master, name):
        self.name = name
        self.master = master
        self.open = False
        self.pendent_messages = 0

    def start_conversation(self):
        if self.open:
            return
        else:
            self.open = True

        super().__init__(self.master, height=400, width=400)

        tk.Label(self, text=f'Conversa com {self.name}').pack(padx=10, pady=10)
        self.scrollText = ScrolledText(self, wrap=tk.WORD, state='disabled')
        self.scrollText.config(height=20, width=50)
        self.scrollText.pack(padx=10, pady=10)

        tk.Label(self, text='Digite uma mensagem:').pack(padx=5)
        self.entry = tk.Entry(self, width=50)
        self.entry.pack(padx=5, pady=5)
        self.entry.bind('<Return>', lambda e: self.send_message())

        server.open_connection(self.name)
        self.pendent_messages = 0
        self.protocol('WM_DELETE_WINDOW', self.close_window)

    def send_message(self, event = None):
        msg = self.entry.get()
        if msg:
            self.entry.delete(0, tk.END)
            server.send_message(msg, self.name, 'contact')
            self.message(f'{client.name}: {msg}')

    def message(self, msg):
        if msg:
            self.scrollText.config(state='normal')
            self.scrollText.insert(tk.END, msg + '\n')
            self.scrollText.see('end')
            self.scrollText.config(state='disabled')

    def close_window(self):
        server.close_connection(self.name)
        self.open = False
        self.destroy()
        client.update()

class Main_menu(tk.Frame):

    contacts = {}
    notify_list = {}

    @Pyro4.expose
    def get_contacts(self):
        return self.contacts

    def __init__(self, master):
        self.master = master
        self.master.geometry('200x150')
        super().__init__(master)
        self.pack(fill='both')

        self.text = tk.Label(self, text='Conectando ao servidor...')
        self.text.pack(padx=10, pady=10)
        self.get_server()

    @threaded
    def get_server(self):
        global server
        try:
            ns = Pyro4.locateNS()
        except:
            self.message_popup('[ERROR] Servidor de nomes não iniciado!')
            return
        server = Pyro4.Proxy(ns.lookup('Server'))

        self.text.config(text='Digite o seu nome: ')
        entry = tk.Entry(self, width=30)
        entry.pack(pady=10)
        self.login_button = tk.Button(self, text='Entrar', command=lambda: self.login(entry.get()))
        self.login_button.pack(side='bottom', pady=10)
        entry.bind('<Return>', lambda event: self.login(entry.get()))
        entry.focus()

    def login(self, name, event = None):
        global server
        if name:
            self.name = name        
        else:
            return
        tk.Label(self, text='Logando...').pack(side='bottom', pady=10)
        self.login_button.config(state='disabled')
        uri = daemon.register(self)
        status = server.start(self.name, uri)
        if status:
            self.destroy()
            self.master.geometry('500x400')
            self.master.title(self.name)
            self.draw_client_window()
            server.notificationQueue()
            self.master.protocol('WM_DELETE_WINDOW', self.disconnect)
        else:
            self.message_popup(f'Cliente {name} já está logado!')

    @threaded
    def draw_client_window(self):
        super().__init__(self.master, height=400, width=500)
        self.pack(fill='x', expand=True)

        self.scrollBar = tk.Scrollbar(self, orient='vertical')
        self.scrollBar.pack(side='right', fill='y')

        self.canvas = tk.Canvas(self, width=450, height=300)
        self.canvas.pack(fill='x')

        self.scrollBar.configure(command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollBar.set)

        tk.Button(self, text='Novo Contato', command=self.add_contact_window).pack(side='left', padx=20, pady=10)
        tk.Button(self, text='Criar Grupo', command=self.create_topic_window).pack(side='left', padx=20, pady=10)
        tk.Button(self, text='Update', command=self.update).pack(side='left', padx=20, pady=10)

        self.draw_client_frame()

    def draw_client_frame(self):
        self.scrollFrame = tk.Frame(self.canvas, bg='white')
        self.scrollFrame.pack(fill='both', expand=True)
        self.scrollFrame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.frame = self.canvas.create_window((0, 0), window=self.scrollFrame, anchor='nw')

        tk.Label(self.scrollFrame, text='Contato').grid(row=0, column=0, padx=5, pady=5)
        tk.Label(self.scrollFrame, text='Tipo').grid(row=0, column=1, padx=5, pady=5)

        if self.contacts == {}:
            tk.Label(self.scrollFrame, text='Você não tem contatos!').grid(row=1, column=0, padx=5, pady=5)
        else:    
            counter = 0
            for contact in self.contacts.values():
                counter += 1
                if isinstance(contact, Contact):
                    tk.Label(self.scrollFrame, text=contact.name).grid(row=counter, column=0, padx=5, pady=5)
                    tk.Label(self.scrollFrame, text='Contato').grid(row=counter, column=1, padx=5, pady=5)
                    tk.Button(self.scrollFrame, text='Iniciar conversa', command=contact.start_conversation).grid(row=counter, column=2, padx=5, pady=5)
                    tk.Button(self.scrollFrame, text='Excluir contato', command=lambda contact=contact: self.delete_contact(contact.name)).grid(row=counter, column=3, padx=5, pady=5)
                elif isinstance(contact, Topic):
                    tk.Label(self.scrollFrame, text=contact.name).grid(row=counter, column=0, padx=5, pady=5)
                    tk.Label(self.scrollFrame, text='Grupo').grid(row=counter, column=1, padx=5, pady=5)
                    tk.Button(self.scrollFrame, text='Entrar', command=contact.open_topic).grid(row=counter, column=2, padx=5, pady=5)
                    tk.Button(self.scrollFrame, text='Sair do grupo', command=lambda contact=contact: self.delete_contact(contact.name)).grid(row=counter, column=3, padx=5, pady=5)
                self.notify_list[contact] = tk.Label(self.scrollFrame)
                self.notify_list[contact].grid(row=counter, column=4, padx=5, pady=5)
                if contact.pendent_messages > 0:
                    if contact.pendent_messages == 1:
                        self.notify_list[contact].config(text='1 mensagem!')
                    else:
                        self.notify_list[contact].config(text=f'{contact.pendent_messages} mensagems!')

    def update(self):
        self.canvas.delete(self.frame)
        self.scrollFrame.destroy()
        self.draw_client_frame()

    @Pyro4.expose
    def notify(self, amount, address):
        if not self.contacts[address].open and amount:
            self.contacts[address].pendent_messages += amount
            try:
                if self.contacts[address].pendent_messages == 1:
                    self.notify_list[address].config('1 mensagem!')
                else:
                    self.notify_list[address].config(f'{self.contacts[address].pendent_messages} mensagems!')
            except:
                pass

    def add_contact_window(self):
        radio_var = tk.StringVar()
        window = tk.Toplevel(self.master, height=200, width=300)
        tk.Label(window, text='Digite o nome do cliente/tópico:').grid(row=0, column=0, padx=5, pady=5)
        ttk.Radiobutton(window, text='Cliente', variable=radio_var, value='client').grid(row=1, column=0, padx=5, pady=5)
        ttk.Radiobutton(window, text='Tópico', variable=radio_var, value='topic').grid(row=1, column=1, padx=5, pady=5)
        entry = tk.Entry(window, width=50)
        entry.grid(row=2, column=0, padx=10, pady=10)
        entry.bind('<Return>', lambda e: self.add_contact(entry.get(), radio_var.get(), window))
        entry.focus()

    def add_contact(self, name, type, window=None, event=None):
        if name and type:
            if name == self.name:
                self.message_popup('Você não pode adicionar a si mesmo!')
                return
            if name in self.contacts.keys():
                self.message_popup('Você já tem esse contato!')
                return
            if type == 'client':
                status = server.new_contact(name)
                if status:
                    self.contacts[name] = Contact(self.master, name)
                    if window:
                        window.destroy()
                    sleep(0.01)
                    self.update()
                else:
                    self.message_popup('Cliente não encontrado!')
                    if window:
                        window.destroy()
            elif type == 'topic':
                if name in server.get_topics.keys():
                    server.new_topic(name)
                    self.contacts[name] = Topic(self.master, name)
                    if window:
                        window.destroy()
                    sleep(0.01)
                    self.update()
                else:
                    self.message_popup('Tópico não encontrado!')
                    if window:
                        window.destroy()

    # Função simplificada para carregar contato pelo servidor
    @Pyro4.expose
    def load_contact(self, name, type):
        if type == 'client':
            self.contacts[name] = Contact(self.master, name)
        elif type == 'topic':
            self.contacts[name] = Topic(self.master, name)

    def create_topic_window(self):
        window = tk.Toplevel(self.master, height=200, width=300)
        tk.Label(window, text='Digite o nome do tópico a ser criado:').pack(padx=5, pady=5)
        entry = tk.Entry(window, width=50)
        entry.pack(padx=10, pady=10)
        entry.bind('<Return>', lambda e: self.create_topic(entry.get(), window))
        entry.focus()

    def create_topic(self, name, window):
        if name:
            if name in server.get_topics.keys():
                self.message_popup('Tópico já existe!')
            else:
                server.new_topic(name)
                self.contacts[name] = Topic(self.master, name)
                self.message_popup('Tópico criado com éxito!')
                window.destroy()
                sleep(0.01)
                self.update()

    def delete_contact(self, name):
        if self.contacts[name].open:
            self.contacts[name].close_window()
        if isinstance(self.contacts[name], Contact):
            server.removeQueue(name, 'contact')
        elif isinstance(self.contacts[name], Topic):
            server.removeQueue(name, 'topic')
        del self.contacts[name]
        sleep(0.01)
        self.update()

    @Pyro4.expose
    @threaded
    def redirect_message(self, msg, origin, topic = None):
        if topic:
            self.contacts[topic].message(f'{origin}: {msg}')
        else:
            try:
                self.contacts[origin].message(f'{origin}: {msg}')
            except:
                self.load_contact(origin, 'contact')
                self.contacts[origin].message(f'{origin}: {msg}')
                self.notify(1, origin)

    @Pyro4.expose
    def message_popup(self, msg):
        popup = tk.Toplevel(self.master, height=200, width=300)
        tk.Label(popup, text=msg).pack(padx=10, pady=10)
        tk.Button(popup, text='Ok', command=popup.destroy).pack(side='bottom', pady=5)
        popup.focus_force()

    def disconnect(self):
        server.logout()
        self.master.quit()
        self.master.destroy()

root = tk.Tk()
client = Main_menu(root)
listen2server()
root.mainloop()
exit()