import pymupdf,re
pdf=pymupdf.open('/home/user/uploads/ESS_Catalogue_General_2026.pdf')
page_map={4:'PAP',6:'ECR',7:'CLA',8:'TAB',9:'EQP',10:'EQP',11:'ORD',12:'INF',13:'ACC',14:'HYG',15:'MOB',16:'EPI'}
allrows=[]
for pn, prefix in page_map.items():
 p=pdf[pn-1]
 words=p.get_text('words',sort=True)
 refs=[]
 for i,w in enumerate(words):
  x0,y0,x1,y1,t,*_=w
  if x0<105:
   if re.fullmatch(r'(?:PAP|ECR|CLA|TAB|EQP|ORD|INF|ACC|HYG|EPI)-\d{3}',t):
    if t.startswith(prefix+'-'): refs.append((y0,t))
   elif prefix=='MOB' and t=='MOB-00':
    following=[ww for ww in words if ww[0]<105 and y0<=ww[1]<y0+15 and ww[4] in list('0123456789')]
    if following:
     refs.append((y0,'MOB-00'+following[0][4]))
 refs.sort()
 print('\nPAGE',pn,prefix,'found refs',len(refs),[r[1] for r in refs[:3]],'...', [r[1] for r in refs[-3:]])
 for i,(start,ref) in enumerate(refs):
  end=refs[i+1][0] if i+1<len(refs) else 760
  ws=[w for w in words if start-0.2<=w[1]<end-0.2]
  cols={k:[] for k in ('desc','pack','price')}
  for x0,y0,x1,y1,t,*_ in ws:
   if x0<105: continue
   key='desc' if x0<365 else 'pack' if x0<490 else 'price'
   cols[key].append((round(y0,1),x0,t))
  out={}
  for k,vals in cols.items():
   vals.sort(key=lambda x:(x[0],x[1]))
   out[k]=' '.join(v[2] for v in vals)
  allrows.append((ref,out))
  print(ref,'|',out)
print('TOTAL',len(allrows))
