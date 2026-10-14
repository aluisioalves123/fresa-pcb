import math
from shapely.geometry import LineString, MultiPolygon
from shapely import affinity
f3=lambda v:f"{v:.3f}"
TOOL=0.35; r=TOOL/2; STEP=TOOL*0.85; PASSES=3; DEPTH=0.2
ilha=LineString([(0,-6),(0,6)]).buffer(1.5,64)      # ilha: barrinha 3 mm x 15 mm
furos_ilha=[(0,-6),(0,6)]
fiduciais=[(-10,0),(10,0)]
TOPO="G53 G0 Z-2"

def caminhos(cu):
    P=[]
    for k in range(PASSES):
        g=cu.buffer(r+k*STEP,64).simplify(0.005)
        for p in (g.geoms if isinstance(g,MultiPolygon) else [g]):
            P.append(list(p.exterior.coords))
    return P

def hull_pts(P):
    pts=sorted(set((round(x,3),round(y,3)) for p in P for x,y in p))
    c=lambda o,a,b:(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[];up=[]
    for p in pts:
        while len(lo)>=2 and c(lo[-2],lo[-1],p)<=0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up)>=2 and c(up[-2],up[-1],p)<=0: up.pop()
        up.append(p)
    H=lo[:-1]+up[:-1]
    return H[::max(1,len(H)//16)]

def voos(P):
    xs=[x for p in P for x,y in p]; ys=[y for p in P for x,y in p]
    x0,x1,y0,y1=min(xs),max(xs),min(ys),max(ys)
    G=["( VOO 1 em cruz, fresa DESLIGADA, Z2: para 2 s em cada extremo, confira se cabe na placa )"]
    for a,b in [((x0,0),(x1,0)),((0,y0),(0,y1))]:
        G+=[f"G0 X{f3(a[0])} Y{f3(a[1])}","G0 Z2","G4 P2",f"G1 X{f3(b[0])} Y{f3(b[1])} F600","G4 P2","G0 Z5"]
    H=hull_pts(P)
    G+=["( VOO 2 no contorno, fresa DESLIGADA, Z0.5 )",f"G0 X{f3(H[0][0])} Y{f3(H[0][1])}","G0 Z0.5","G4 P2"]
    G+=[f"G1 X{f3(x)} Y{f3(y)} F600" for x,y in H[1:]+[H[0]]]
    G+=["G4 P2",TOPO,"G0 X0 Y0","( PAUSA: aperte Pause de novo no Candle para continuar, ou Stop para cancelar )","M0"]
    return G

def iso(nome,titulo,lado):
    P=caminhos(ilha)
    G=[f"( {titulo} )",f"( V-bit 30 graus | {PASSES} passadas | profundidade {DEPTH} )",
       "( zero XY: G54 apos homing | zero Z: probe no cobre )","G21 G90 G17",TOPO]
    G+=voos(P)+["M3 S1000","G4 P3"]
    for p in P:
        G+=[f"G0 X{f3(p[0][0])} Y{f3(p[0][1])}","G0 Z1",f"G1 Z-{DEPTH} F30"]
        G+=[f"G1 X{f3(x)} Y{f3(y)} F100" for x,y in p[1:]]+["G0 Z2"]
    G+=[TOPO,"M5","G0 X0 Y0","M30"]
    open(nome,'w').write("\n".join(G)+"\n")

def furos(nome,titulo,holes):
    G=[f"( {titulo} )","( broca 0.8 | atravessa subindo a cada 0.4 mm )","( zero Z: probe no cobre com a broca )",
       "G21 G90 G17",TOPO,"M3 S1000","G4 P3"]
    for x,y in holes:
        G+=[f"G0 X{f3(x)} Y{f3(y)}","G0 Z0.5"]
        z=0
        while z>-2.0:
            z=max(z-0.4,-2.0); G+=[f"G1 Z{z:.2f} F30","G0 Z0.5"]
        G+=["G0 Z2"]
    G+=[TOPO,"M5","G0 X0 Y0","M30"]
    open(nome,'w').write("\n".join(G)+"\n")

iso("T1-ilha-cima.nc","TESTE ALINHAMENTO: ilha do lado de CIMA","cima")
furos("T2-furos-ilha-e-fiduciais.nc","TESTE ALINHAMENTO: 2 furos da ilha e 2 fiduciais",furos_ilha+fiduciais)
iso("T3-ilha-baixo-SEM-CORRECAO.nc","TESTE ALINHAMENTO: ilha do lado de BAIXO, placa virada, SEM correcao","baixo")
