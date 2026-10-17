"""Build deterministic public interview edits from verified existing masters."""
from pathlib import Path
import argparse, hashlib, json, math, re, subprocess
ASSETS = {
 'gvf': ('1V_e4cjXccaNJaVdRCUxq8zMIA4H2Ipwa',2443369,'fbe37717a69bab85afb24e818e93cb07d70467afc3100ba108a07747f1a44d3d'),
 'studios': ('1JfYVQrDxO_aMb6uqQfYI7MOl8mEqllt-',1337452,'52b3d1b6a2eab7e2701f93dddd85c51b5af7d8cee326299d95fb2f1d160837f1'),
 'logo': ('1s09LnxmhH5utRcp-LZcSdW7dsUS7QzXw',264878,'b7d40e0c672f9bae8a7e3023698f8c2a192999f76a44b115258fa1b80da41d72')}
CONFIG = {
 'keyze': {'source': ('1mXUEIF-ceKCRgRIMdMRGfbemOa68hezN',780243293,'06822cfa34dde647e4c9359077f4c204568048fb50aeae77e9f063260c1b279746'),
 'full': [('source',12.5,118.1),('source',270.6,727),('gvf',0,12),('source',727,1299.4),('studios',0,25),('source',1299.4,1986.65)],
 'feature': [('source',370.7,727),('gvf',0,12),('source',727,963.52)], 'title': 'Keyze AriZona',
 'note': 'Known reconnection interval 118.1-270.6 seconds excluded; original retained. Feature: Christmas in Spring, filmmaking and creative partnerships.'},
 'just-emcee': {'source': ('1z843OIlgokyeP6TKoqBWkXpTHc2xLU6E',924842933,'510326981b2c4656c9298b3e45c87d55e4d5ee3b1c51479372e8c32043847b993f'),
 'full': [('source',4.7,680.5),('gvf',0,12),('source',680.5,1427),('studios',0,25),('source',1427,2355.7)],
 'feature': [('source',680.7,1038),('studios',0,25),('source',1038,1307.5)], 'title': 'Just Emcee',
 'note': 'Original recording and private clean delivery retained. Feature: consistency, catalog growth, criticism and client collaboration.'},
 'austin-je': {'source': ('17w2CbdgbYzuFe8PDix3YiVrpuxGg_jpH',1840772394,'2c8db57d505aa8c72d5bf65b6c49fa85cd68ac4a2a74033df657f542d8ef9622'),
 'full': [('source',0,1545.97),('gvf',0,12),('source',1545.97,2922.65),('studios',0,25),('source',2922.65,4254.733333)],
 'feature': [('source',2128.3,2541.7),('studios',0,25),('source',2541.7,2742.1)], 'title': 'Austin Je',
 'note': 'Uses the V5 REMOTION_SYNC_FIXED master. Its established internal AV relationship is retained; no extra audio offset. Feature: performance tracks, breath control and preparing a live set.'}}

def timeline(parts):
    if not parts: raise ValueError('Empty edit')
    result={'duration':0.0,'ads':[],'segments':[]}
    for name,start,end in parts:
        if name not in ('source','gvf','studios') or start<0 or end<=start: raise ValueError('Invalid edit range')
        item={'asset':name,'source_start':start,'source_end':end,'start':result['duration'],'duration':end-start}
        result['segments'].append(item)
        if name!='source': result['ads'].append(dict(item))
        result['duration']+=end-start
    return result

def run(args, log=None):
    if log:
        with open(log,'w') as f: subprocess.run(args,check=True,stdout=f,stderr=subprocess.STDOUT)
    else: subprocess.run(args,check=True)

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def download(meta,path):
    ident,size,sha=meta
    run(['gdown',ident,'--no-cookies','-O',str(path)])
    if path.stat().st_size!=size or digest(path)!=sha: raise ValueError(f'Source size/hash mismatch: {path}')

def loudness(path,log):
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-i',str(path),'-vn','-af','highpass=f=65,loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
    Path(log).write_text(p.stderr)
    v=json.loads(re.findall(r'\{\s*"input_i".*?\}',p.stderr,re.S)[-1])
    if not all(math.isfinite(float(v[k])) for k in ['input_i','input_tp','input_lra','input_thresh','target_offset']): raise ValueError('Invalid audio measurement')
    return (f"highpass=f=65,loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={v['input_i']}:measured_TP={v['input_tp']}:measured_LRA={v['input_lra']}:measured_thresh={v['input_thresh']}:offset={v['target_offset']}:linear=true")

def encode_piece(src,logo,start,duration,audio_filter,out,is_ad=False):
    frames=round(duration*30);duration=frames/30
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','warning','-y','-ss',str(start),'-i',str(src)]
    if not is_ad:cmd+=['-loop','1','-i',str(logo)]
    video='[0:v]setpts=PTS-STARTPTS,fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p'
    if not is_ad:video+='[base];[1:v]scale=110:110[bug];[base][bug]overlay=W-w-18:18:shortest=1'
    filt=video+f'[v];[0:a]asetpts=PTS-STARTPTS,{audio_filter},aresample=48000,apad,atrim=duration={duration}[a]'
    cmd+=['-filter_complex_threads','1','-filter_complex',filt,'-map','[v]','-map','[a]','-t',str(duration),'-frames:v',str(frames),'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-g','60','-c:a','pcm_s16le','-ar','48000','-ac','2','-threads','4',str(out)]
    run(cmd,str(out)+'.log');return duration

def assemble(parts,inputs,filters,out,qa,work):
    listing=[];exact=[]
    for i,(name,start,end) in enumerate(parts):
        path=work/f'{out.stem}_{i:02d}.mkv'
        d=encode_piece(inputs[name],inputs['logo'],start,end-start,filters[name],path,name!='source')
        listing += [f"file '{path.resolve()}'",f'duration {d:.9f}'];exact.append((name,start,start+d))
    concat=work/f'{out.stem}.txt';concat.write_text('\n'.join(listing)+'\n')
    run(['ffmpeg','-nostdin','-hide_banner','-loglevel','warning','-y','-f','concat','-safe','0','-i',str(concat),'-map','0:v:0','-map','0:a:0','-c:v','copy','-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-movflags','+faststart',str(out)],qa/f'{out.stem}-mux.log')
    info=timeline(exact);info.update(file=out.name,bytes=out.stat().st_size,sha256=digest(out),probe=probe(out))
    duration=float(info['probe']['format']['duration'])
    if abs(duration-info['duration'])>0.25:raise ValueError('Unexpected assembled duration')
    run(['ffmpeg','-nostdin','-hide_banner','-v','error','-xerror','-i',str(out),'-map','0:v:0','-map','0:a:0','-f','null','-'],qa/f'{out.stem}-decode.log');info['full_decode']='PASS'
    run(['ffmpeg','-nostdin','-hide_banner','-i',str(out),'-vn','-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'],qa/f'{out.stem}-audio.log')
    times=[1,duration-2]
    for ad in info['ads']:times += [max(0,ad['start']-1),ad['start']+1,ad['start']+ad['duration']/2,ad['start']+ad['duration']-1,ad['start']+ad['duration']+1]
    for j,stamp in enumerate(sorted(set(times))):run(['ffmpeg','-nostdin','-v','error','-y','-ss',str(stamp),'-i',str(out),'-frames:v','1','-vf','scale=640:-2',str(qa/f'{out.stem}-frame-{j:02d}-{stamp:.2f}.jpg')])
    for j,ad in enumerate(info['ads']):run(['ffmpeg','-nostdin','-v','error','-y','-ss',str(max(0,ad['start']-3)),'-i',str(out),'-t',str(ad['duration']+6),'-vf','scale=640:-2','-c:v','libx264','-preset','veryfast','-crf','25','-c:a','aac','-b:a','96k',str(qa/f'{out.stem}-ad-join-{j+1}.mp4')])
    for path in work.glob(f'{out.stem}_*.mkv'):path.unlink()
    return info

def main():
    ap=argparse.ArgumentParser();ap.add_argument('name',choices=CONFIG);args=ap.parse_args();cfg=CONFIG[args.name]
    qa=Path('qa');qa.mkdir(exist_ok=True);outdir=Path('outputs');outdir.mkdir(exist_ok=True);work=Path('work');work.mkdir(exist_ok=True)
    inputs={}
    for name,meta in {'source':cfg['source'],**ASSETS}.items():
        path=work/(name+('.jpg' if name=='logo' else '.mp4'));download(meta,path);inputs[name]=path
    filters={k:loudness(inputs[k],qa/f'{k}-loudness.log') for k in ('source','gvf','studios')}
    manifest={'interview':cfg['title'],'note':cfg['note'],'source_sha256':cfg['source'][2],'ads':{k:v[2] for k,v in ASSETS.items() if k!='logo'},'logo_sha256':ASSETS['logo'][2],'outputs':[],'scope':'Public social derivatives only; private guest delivery and original files unchanged.'}
    for kind in ('feature','full'):
        out=outdir/f'{args.name}_{kind}_{1 if kind=="feature" else 2}ads_720p.mp4'
        info=assemble(cfg[kind],inputs,filters,out,qa,work)
        if len(info['ads'])!=(1 if kind=='feature' else 2):raise ValueError('Incorrect ad count')
        if kind=='feature' and not 480<=info['duration']<=720:raise ValueError('Feature length out of range')
        manifest['outputs'].append(info);(qa/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (qa/'SUCCESS.txt').write_text('Both public editions rendered and complete decode passed. Visual/ad/audio evidence accompanies the files. No native social publication is implied.\n')
    for row in manifest['outputs']:print(row['file'],row['duration'],row['bytes'],row['sha256'])
if __name__=='__main__':main()
