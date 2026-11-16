import math
def wgs84_to_osgb(lat, lon):
    # WGS84 -> cartesian
    a,b=6378137.0,6356752.3141; e2=1-(b*b)/(a*a)
    φ,λ=math.radians(lat),math.radians(lon); H=0
    ν=a/math.sqrt(1-e2*math.sin(φ)**2)
    x=(ν+H)*math.cos(φ)*math.cos(λ); y=(ν+H)*math.cos(φ)*math.sin(λ); z=((1-e2)*ν+H)*math.sin(φ)
    # Helmert WGS84 -> OSGB36
    tx,ty,tz=-446.448,125.157,-542.060; s=20.4894e-6
    rx,ry,rz=[math.radians(v/3600) for v in (-0.1502,-0.2470,-0.8421)]
    x2=tx+(1+s)*x+(-rz)*y+(ry)*z; y2=ty+(rz)*x+(1+s)*y+(-rx)*z; z2=tz+(-ry)*x+(rx)*y+(1+s)*z
    # cartesian -> Airy 1830 lat/lon
    a,b=6377563.396,6356256.909; e2=1-(b*b)/(a*a)
    p=math.sqrt(x2*x2+y2*y2); φ=math.atan2(z2,p*(1-e2))
    for _ in range(10):
        ν=a/math.sqrt(1-e2*math.sin(φ)**2); φ=math.atan2(z2+e2*ν*math.sin(φ),p)
    λ=math.atan2(y2,x2)
    # Transverse Mercator (National Grid)
    F0=0.9996012717; φ0=math.radians(49); λ0=math.radians(-2); N0,E0=-100000,400000
    n=(a-b)/(a+b); ν=a*F0/math.sqrt(1-e2*math.sin(φ)**2); ρ=a*F0*(1-e2)/(1-e2*math.sin(φ)**2)**1.5; η2=ν/ρ-1
    Ma=(1+n+5/4*n**2+5/4*n**3)*(φ-φ0); Mb=(3*n+3*n**2+21/8*n**3)*math.sin(φ-φ0)*math.cos(φ+φ0)
    Mc=(15/8*n**2+15/8*n**3)*math.sin(2*(φ-φ0))*math.cos(2*(φ+φ0)); Md=35/24*n**3*math.sin(3*(φ-φ0))*math.cos(3*(φ+φ0))
    M=b*F0*(Ma-Mb+Mc-Md); c,s_,t=math.cos(φ),math.sin(φ),math.tan(φ)
    I=M+N0; II=ν/2*s_*c; III=ν/24*s_*c**3*(5-t*t+9*η2); IIIA=ν/720*s_*c**5*(61-58*t*t+t**4)
    IV=ν*c; V=ν/6*c**3*(ν/ρ-t*t); VI=ν/120*c**5*(5-18*t*t+t**4+14*η2-58*t*t*η2)
    dλ=λ-λ0
    N=I+II*dλ**2+III*dλ**4+IIIA*dλ**6; E=E0+IV*dλ+V*dλ**3+VI*dλ**5
    return E,N
def gridref(lat,lon,digits=6):
    E,N=wgs84_to_osgb(lat,lon)
    e100k,n100k=int(E//100000),int(N//100000)
    l1=(19-n100k)-(19-n100k)%5+(e100k+10)//5; l2=((19-n100k)*5)%25+e100k%5
    if l1>7: l1+=1
    if l2>7: l2+=1
    letters=chr(l1+65)+chr(l2+65); d=digits//2
    e=int((E%100000)//10**(5-d)); n=int((N%100000)//10**(5-d))
    return f"{letters} {e:0{d}d} {n:0{d}d}"
if __name__=='__main__':
    import sys
    for s in sys.argv[1:]:
        la,lo=map(float,s.split(',')); print(s, gridref(la,lo), '%.0f %.0f'%wgs84_to_osgb(la,lo))
