#!/usr/bin/env python3
"""Tableau framebuffer pour l'A5, police Terminus agrandie x1.5, sans dependances."""
import os,fcntl,struct,mmap,time,ctypes,gzip,socket,re,subprocess,shutil,signal,sys,zlib,selectors
from pathlib import Path
class Fix(ctypes.Structure):
    _fields_=[('id',ctypes.c_char*16),('smem_start',ctypes.c_ulong),('smem_len',ctypes.c_uint32),('type',ctypes.c_uint32),('type_aux',ctypes.c_uint32),('visual',ctypes.c_uint32),('xpanstep',ctypes.c_uint16),('ypanstep',ctypes.c_uint16),('ywrapstep',ctypes.c_uint16),('line_length',ctypes.c_uint32),('mmio_start',ctypes.c_ulong),('mmio_len',ctypes.c_uint32),('accel',ctypes.c_uint32),('capabilities',ctypes.c_uint16),('reserved',ctypes.c_uint16*2)]
def read(p,default=''):
    try:return Path(p).read_text().strip()
    except (OSError,UnicodeError):return default
HOME_CODES=(102,172)
POWER=116; VOLUME_UP=115; VOLUME_DOWN=114
BUTTON_CODES=HOME_CODES+(POWER,VOLUME_UP,VOLUME_DOWN)
SCREEN_TIMEOUT=300
EVENT=struct.Struct('@llHHi')
def key_mask(keys):
    return sum(int(word,16) << (i*ctypes.sizeof(ctypes.c_ulong)*8) for i,word in enumerate(reversed(keys.split())))
def has_home(keys):
    try:
        mask=key_mask(keys)
        return any(mask & (1<<code) for code in HOME_CODES)
    except ValueError:return False
def home_press(event):
    _,_,kind,code,value=event
    return kind==1 and code in HOME_CODES and value==1
class IdleState:
    def __init__(self,now):self.deadline=now+SCREEN_TIMEOUT
    def pressed(self,now):self.deadline=now+SCREEN_TIMEOUT
    def expired(self,now):return now>=self.deadline
class HomeInputs:
    def __init__(self):
        self.selector=selectors.DefaultSelector();self.names=[];self.buffers={};self.codes=set()
        for device in sorted(Path('/sys/class/input').glob('event*')):
            keys=read(device/'device/capabilities/key')
            if not has_home(keys):continue
            node='/dev/input/'+device.name
            try:fd=os.open(node,os.O_RDONLY|os.O_NONBLOCK)
            except OSError:continue
            self.selector.register(fd,selectors.EVENT_READ);self.buffers[fd]=b''
            mask=key_mask(keys);self.codes.update(c for c in BUTTON_CODES if mask & (1<<c))
            self.names.append(node+' : '+read(device/'device/name','nom inconnu'))
    def wait(self,seconds):
        pressed=[]
        for key,_ in self.selector.select(seconds):
            fd=key.fd
            try:data=os.read(fd,EVENT.size*64)
            except BlockingIOError:continue
            except OSError:data=b''
            if not data:
                self.selector.unregister(fd);os.close(fd);self.buffers.pop(fd,None);continue
            data=self.buffers[fd]+data
            n=len(data)//EVENT.size
            for i in range(n):
                _,_,kind,code,value=EVENT.unpack_from(data,i*EVENT.size)
                if kind==1 and code in BUTTON_CODES and value==1:pressed.append(code)
            self.buffers[fd]=data[n*EVENT.size:]
        return pressed
    def close(self):
        for fd in list(self.buffers):os.close(fd)
        self.buffers.clear();self.selector.close()
class Menu:
    def __init__(self):self.page=None;self.index=0;self.message='';self.wifi_enabled=True;self.pending=False
    def items(self):
        if self.page=='reboot':
            return [('Retour','back'),('Redemarrer','normal'),('Recovery (TWRP)','recovery'),('Download mode','download'),('Mode secours','rescue')]
        return [('Retour','back'),('Eteindre','poweroff'),('Redemarrer...','submenu'),
                ('Desactiver le Wi-Fi' if self.wifi_enabled else 'Activer le Wi-Fi','wifi')]
    def press(self,code):
        if self.pending:return None
        if code==POWER and self.page is None:
            self.page='main';self.index=0;self.message='';return 'opened'
        if self.page is None:return None
        if code in (VOLUME_UP,VOLUME_DOWN):
            self.index=(self.index+(-1 if code==VOLUME_UP else 1))%len(self.items());return None
        if code!=POWER:return None
        action=self.items()[self.index][1]
        if action=='back':self.page='main' if self.page=='reboot' else None;self.index=0
        elif action=='submenu':self.page='reboot';self.index=0
        else:return action
        return None
    def lines(self):
        return ['REDEMARRAGE' if self.page=='reboot' else 'MENU TELEPHONE',socket.gethostname(),'']+[
            ('> ' if i==self.index else '  ')+label for i,(label,_) in enumerate(self.items())]+[
            '',self.message,'','Volume haut : monter','Volume bas : descendre','Power : confirmer','Home : veille / reveil']

def wifi_enabled():
    try:return subprocess.check_output(['nmcli','radio','wifi'],text=True,timeout=2,env={**os.environ,'LC_ALL':'C'}).strip()=='enabled'
    except (OSError,subprocess.SubprocessError):return True

def action_command(action,enabled):
    if action=='wifi':return ['nmcli','radio','wifi','off' if enabled else 'on']
    if action=='poweroff':return ['/sbin/poweroff']
    if action in ('normal','recovery','download','rescue'):return ['/sbin/reboot']
    raise ValueError('Action inconnue')

def execute_action(menu,action):
    modefile=Path('/run/telephone-dashboard-reboot-mode')
    rescue=Path('/var/lib/telephone-dashboard/rescue-next-boot')
    try:
        if action=='wifi':
            subprocess.run(action_command(action,menu.wifi_enabled),check=True,timeout=8,stdout=subprocess.DEVNULL)
            menu.wifi_enabled=wifi_enabled();menu.message='Wi-Fi active' if menu.wifi_enabled else 'Wi-Fi desactive'
        else:
            # Marqueurs lus pendant l'arret / au prochain boot. Aucun flash.
            modefile.unlink(missing_ok=True)
            if action in ('recovery','download'):modefile.write_text(action+'\n')
            if action=='rescue':rescue.parent.mkdir(parents=True,exist_ok=True);rescue.write_text(read('/proc/sys/kernel/random/boot_id')+'\n')
            subprocess.run(action_command(action,menu.wifi_enabled),check=True,timeout=8,stdout=subprocess.DEVNULL)
            menu.pending=True;menu.message='Extinction...' if action=='poweroff' else 'Redemarrage...'
    except (OSError,subprocess.SubprocessError) as err:
        if action!='wifi':
            modefile.unlink(missing_ok=True)
            if action=='rescue':rescue.unlink(missing_ok=True)
        menu.message='Echec : voir le journal';print('Action',action,err,flush=True)

class ScreenPower:
    def __init__(self,fb):
        self.fb=fb;self.asleep=False
        self.brightness=Path('/sys/class/backlight/panel/brightness')
        self.saved=read(self.brightness)
    def set(self,asleep):
        try:fcntl.ioctl(self.fb,0x4611,4 if asleep else 0)
        except OSError as err:print('FBIOBLANK:',err,flush=True)
        if self.saved:
            try:self.brightness.write_text('0' if asleep else self.saved)
            except OSError as err:print('Luminosite:',err,flush=True)
        self.asleep=asleep
        print('Ecran en veille' if asleep else 'Ecran allume',flush=True)
class Font:
    def __init__(self,path):
        raw=gzip.decompress(Path(path).read_bytes());head=struct.unpack_from('<8I',raw)
        magic,version,offset,flags,count,self.size,self.height,self.width=head
        if magic!=0x864ab572 or not (self.width==16 and self.height==32):raise ValueError('Police PSF2 16x32 attendue')
        self.raw=raw[offset:offset+count*self.size];self.mapping={};self.cache={}
        if flags&1:
            table=raw[offset+count*self.size:]
            for index,item in enumerate(table.split(b'\xff')[:count]):
                for c in item.split(b'\xfe')[0].decode('utf-8',errors='ignore'):self.mapping[c]=index
        else:self.mapping={chr(i):i for i in range(min(count,128))}
    def glyph(self,c,fg,bg):
        key=(c,fg,bg)
        if key in self.cache:return self.cache[key]
        index=self.mapping.get(c,self.mapping.get('?',0));data=self.raw[index*self.size:(index+1)*self.size]
        result=[]
        for y in range(48):
            source_y=y*32//48
            value=int.from_bytes(data[source_y*2:source_y*2+2],'big')
            row=b''.join(fg if value&(1<<(15-(x*16//24))) else bg for x in range(24))
            result.append(row)
        self.cache[key]=result;return result
FG=bytes((255,255,255,255));ACCENT=FG;BG=bytes((0,0,0,255))
def render(font,w,h,lines):
    frame=bytearray(BG*(w*h));left=48;top=48;pitch=60;columns=(w-left*2)//24
    for row,text in enumerate(lines):
        y=top+row*pitch
        if y+48>h:break
        colour=ACCENT if row in (0,1,23) else FG
        for col,c in enumerate(text[:columns]):
            x=left+col*24
            for dy,pixels in enumerate(font.glyph(c,colour,BG)):
                pos=((y+dy)*w+x)*4;frame[pos:pos+len(pixels)]=pixels
    return frame
last_cpu=None
def metrics():
    global last_cpu
    words=read('/proc/stat').splitlines()[0].split()[1:9];values=list(map(int,words));total=sum(values);idle=values[3]+values[4]
    cpu=0 if last_cpu is None or total<=last_cpu[0] else max(0,min(100,100*(1-(idle-last_cpu[1])/(total-last_cpu[0]))))
    last_cpu=(total,idle)
    mem={m.group(1):int(m.group(2)) for m in re.finditer(r'^(\w+):\s+(\d+)',read('/proc/meminfo'),re.M)}
    totalram=mem.get('MemTotal',0);available=mem.get('MemAvailable',mem.get('MemFree',0)+mem.get('Buffers',0)+mem.get('Cached',0));used=max(0,totalram-available)
    addresses='';state='Indisponible'
    try:
        state=subprocess.check_output(['nmcli','-g','GENERAL.STATE','device','show','wlan0'],text=True,timeout=2).strip()
        addresses=subprocess.check_output(['nmcli','-g','IP4.ADDRESS','device','show','wlan0'],text=True,timeout=2).strip()
    except (OSError,subprocess.SubprocessError):pass
    ip=re.search(r'(\d+\.\d+\.\d+)\.\d+',addresses);masked=ip.group(1)+'.xxx' if ip else 'Indisponible'
    wifi='Connecte' if state.startswith('100') else 'Deconnecte'
    uptime=float(read('/proc/uptime','0 0').split()[0]);disk=shutil.disk_usage('/')
    totaldisk=read('/sys/class/block/mmcblk0/size');capacity=f'{int(totaldisk)*512/2**30:.1f} Gio' if totaldisk.isdigit() else 'Indisponible'
    thermal=[]
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        kind=read(zone/'type').lower();value=read(zone/'temp')
        if any(k in kind for k in ('cpu','exynos','cluster','big','little','soc','tmu')):
            try:
                t=float(value)/1000
                if 0<t<150:thermal.append(t)
            except ValueError:pass
    temp=f'{max(thermal):.1f} C' if thermal else 'Indisponible'
    supply=Path('/sys/class/power_supply/battery')
    if not supply.exists():supply=next((p for p in Path('/sys/class/power_supply').glob('*') if read(p/'type')=='Battery'),supply)
    battery=read(supply/'capacity');battery=battery+' %' if battery.isdigit() else 'Indisponible'
    charge={'Charging':'En charge','Discharging':'Sur batterie','Full':'Pleine','Not charging':'Charge suspendue'}.get(read(supply/'status'),'Etat inconnu')
    try:bt=f'{int(read(supply/"temp"))/10:.1f} C'
    except ValueError:bt='Indisponible'
    return [
      'SAMSUNG GALAXY A5',socket.gethostname()[:32],'',
      time.strftime('%d/%m/%Y  %H:%M:%S'),time.strftime('Fuseau : %Z'),
      f'Uptime : {int(uptime//3600)}h {int(uptime%3600//60):02d}min','',
      'Wi-Fi : '+wifi,'IP : '+masked,'',
      f'CPU : {cpu:.0f} %','Temp CPU/SoC : '+temp,'',
      f'RAM : {used/1024:.0f}/{totalram/1024:.0f} Mio',f'RAM utilisee : {100*used/totalram:.0f} %' if totalram else 'RAM indisponible','',
      f'Systeme : {disk.used/2**20:.0f} Mio',f'Systeme total : {disk.total/2**20:.0f} Mio','Stockage : '+capacity,'',
      'Batterie : '+battery,charge,'Temp batterie : '+bt,
      'Home : veille / reveil','Power : menu']
def write_png(path,w,h,pixels):
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    raw=b''.join(b'\0'+pixels[y*w*4:(y+1)*w*4] for y in range(h))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))
def main():
    path='/usr/share/consolefonts/ter-132b.psf.gz'
    if len(sys.argv)>1 and sys.argv[1]=='--console':
        with open('/dev/fb0','r+b',buffering=0) as fb:fcntl.ioctl(fb,0x4611,0)
        brightness=Path('/sys/class/backlight/panel/brightness')
        if read(brightness)=='0':brightness.write_text('128')
        tty=os.open('/dev/tty1',os.O_RDWR)
        fcntl.ioctl(tty,0x4B3A,0)
        os.write(tty,b'\033[0m\033[2J\033[HMode secours - console locale et services reseau\r\n')
        os.close(tty);return
    if len(sys.argv)>1 and sys.argv[1] in ('--check-home','--check-buttons'):
        inputs=HomeInputs()
        for name in inputs.names:print('Bouton Home disponible :',name)
        found=bool(inputs.names)
        if sys.argv[1]=='--check-buttons':
            found=found and all(c in inputs.codes for c in (POWER,VOLUME_UP,VOLUME_DOWN))
            print('Codes des boutons accessibles :',sorted(inputs.codes))
        inputs.close()
        if not found:raise SystemExit('Aucun bouton Home accessible : veille non installee.')
        return
    if len(sys.argv)>1 and sys.argv[1]=='--preview-menu':
        menu=Menu();menu.press(POWER)
        lines=menu.lines();lines[1]='samsung-a5y17lte'
        write_png(sys.argv[3],1080,1920,render(Font(sys.argv[2]),1080,1920,lines));return
    if len(sys.argv)>1 and sys.argv[1]=='--preview':
        font=Font(sys.argv[2]);lines=['SAMSUNG GALAXY A5','samsung-a5y17lte','','03/10/2026  20:55:00','Fuseau : CEST','Uptime : 0h 12min','','Wi-Fi : Connecte','IP : 192.168.1.xxx','','CPU : 8 %','Temp CPU/SoC : Indisponible','','RAM : 109/2829 Mio','RAM utilisee : 4 %','','Systeme : 156 Mio','Systeme total : 4450 Mio','Stockage : 29.1 Gio','','Batterie : 43 %','En charge','Temp batterie : 28.7 C','Home : veille / reveil']
        assert max(map(len,lines))<=32
        write_png(sys.argv[3],1080,1920,render(font,1080,1920,lines));return
    if os.geteuid()!=0:raise SystemExit('Utiliser sudo.')
    font=Font(path)
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    with open('/dev/fb0','r+b',buffering=0) as fb:
        var=bytearray(160);fcntl.ioctl(fb,0x4600,var,True)
        raw=bytearray(ctypes.sizeof(Fix));fcntl.ioctl(fb,0x4602,raw,True);fix=Fix.from_buffer_copy(raw)
        w,h,vw,vh,xoff,yoff,bpp=struct.unpack_from('=7I',var);stride=fix.line_length
        if bpp!=32 or (w,h)!=(1080,1920) or stride<w*4:raise RuntimeError('Framebuffer A5 inattendu : aucun dessin.')
        start=yoff*stride+xoff*4;end=start+(h-1)*stride+w*4
        if not 0<end<=fix.smem_len:raise RuntimeError('Taille framebuffer incoherente.')
        tty=os.open('/dev/tty1',os.O_RDWR);oldmode=bytearray(4);fcntl.ioctl(tty,0x4B3B,oldmode,True);previous=struct.unpack('=I',oldmode)[0]
        inputs=HomeInputs();power=ScreenPower(fb)
        policy=IdleState(time.monotonic());menu=Menu()
        try:
            fcntl.ioctl(tty,0x4B3A,1);power.set(False)
            print('Veille apres 300 secondes ; appui Home pour eteindre ou rallumer.',flush=True)
            if not inputs.names:print('Bouton Home absent : veille desactivee.',flush=True)
            with mmap.mmap(fb.fileno(),fix.smem_len,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE) as screen:
                while True:
                    tick=time.monotonic()
                    if inputs.buffers and policy.expired(tick) and not power.asleep and not menu.pending:
                        menu.page=None;power.set(True)
                    if not power.asleep:
                        frame=render(font,w,h,menu.lines() if menu.page else metrics())
                        for y in range(h):screen[start+y*stride:start+y*stride+w*4]=frame[y*w*4:(y+1)*w*4]
                        fcntl.ioctl(fb,0x4606,var,True)
                    # Sans bouton accessible, garder l'ecran allume.
                    if power.asleep and not inputs.buffers:power.set(False)
                    delay=2 if power.asleep else max(0.1,2-(time.monotonic()-tick))
                    for code in inputs.wait(delay):
                        policy.pressed(time.monotonic())
                        if code in HOME_CODES:
                            if not menu.pending:menu.page=None;power.set(not power.asleep)
                        else:
                            if power.asleep and code!=POWER:continue
                            if power.asleep:power.set(False)
                            action=menu.press(code)
                            if action=='opened':menu.wifi_enabled=wifi_enabled()
                            elif action:execute_action(menu,action)
        except KeyboardInterrupt:pass
        finally:
            power.set(False);inputs.close()
            fcntl.ioctl(tty,0x4B3A,previous);os.close(tty)
if __name__=='__main__':main()
