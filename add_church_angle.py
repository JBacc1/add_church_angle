from osmdata import *
import sys
import osm2shapely
#from add_angles import calcul_angle
from scipy.optimize import differential_evolution

print_to_osm=True #prints intermediate objects to the osm file

def calcul_angle(a,b):
	"""Calcule l'angle à partir de deux nœuds"""
#   θ = atan2(sin(Δlong)*cos(lat2), cos(lat1)*sin(lat2) − sin(lat1)*cos(lat2)*cos(Δlong))
	DLong=-a.location.x+b.location.x
	angle= (360+((-math.atan2(math.sin(DLong)*math.cos(b.location.y), math.cos(a.location.y)*math.sin(b.location.y) - math.sin(a.location.y)*math.cos(b.location.y)*math.cos(DLong))) /math.pi*180))%360
	angle= (360+(-math.degrees(math.atan2(math.sin(math.radians(DLong))*math.cos(math.radians(b.location.y)), math.cos(math.radians(a.location.y))*math.sin(math.radians(b.location.y)) - math.sin(math.radians(a.location.y))*math.cos(math.radians(b.location.y))*math.cos(math.radians(DLong)) ) )))%360

#	print(angle)
	return angle


def make_sub_rectangle(rectangle,a,b):
	"""returns a subrectangle with a and b between 0 and 1, along the long side of the rectangle. If a==b, returns a LineString. If a<0, acts as if a==0, idem if b>1"""
	if a<0 or b>1: print("in make_sub_rectangle, a or b outside [0,1], unusual use:"+str(a)+","+str(b))

#find long sides of rectangle	
	if osm2shapely.shapely.geometry.Point(rectangle.exterior.coords[0]).distance(osm2shapely.shapely.geometry.Point(rectangle.exterior.coords[1]))>osm2shapely.shapely.geometry.Point(rectangle.exterior.coords[2]).distance(osm2shapely.shapely.geometry.Point(rectangle.exterior.coords[1])): 
		i=0
	else: 
		i=1
	long_side1=osm2shapely.shapely.geometry.LineString([osm2shapely.shapely.geometry.Point(rectangle.exterior.coords[i]),osm2shapely.shapely.geometry.Point(rectangle.exterior.coords[i+1])])
	long_side2=osm2shapely.shapely.geometry.LineString([osm2shapely.shapely.geometry.Point(rectangle.exterior.coords[i+3]),osm2shapely.shapely.geometry.Point(rectangle.exterior.coords[i+2])])
	
	short_cut1=osm2shapely.shapely.geometry.LineString([long_side1.interpolate(a,True),long_side2.interpolate(a,True)])
	short_cut2=osm2shapely.shapely.geometry.LineString([long_side1.interpolate(b,True),long_side2.interpolate(b,True)])
	
	r=osm2shapely.shapely.geometry.MultiLineString([short_cut1,short_cut2])
	return r.convex_hull
def to_minimize(x,mrr,polygon_church,mina=0.1,maxa=0.9,negative_factor=7):
	"""function to be minimized to find the transept"""
	[a,b]=x
	out=0
	if a<mina:
		out+=10000*(mina-a)
	if b>maxa:
		out+=10000*(b-maxa)
	if b<=a:
		out+=100000+(a-b)*10000
	if out==0:
		out=-((polygon_church.intersection(make_sub_rectangle(mrr,x[0],x[1]))).area - negative_factor*make_sub_rectangle(mrr,x[0],x[1]).difference(polygon_church).area)
		out-=b-a
	return out
def callback_differential_evolution(xk,convergence):
	print(xk,end="  ")

	
try : in_file=sys.argv[1]
except: 
	print("Usage : python add_church_angle.py infile.osm")
	sys.exit()

print('Chargement du fichier : '+in_file)
osm = OsmData()
osm.load_xml_file(in_file)
osm.upload="never"

print('Traitement des éléments')
nb_church=len(osm.find_ways(lambda x: (x.has_tag("amenity","place_of_worship")))+osm.find_relations(lambda x: (x.has_tag("amenity","place_of_worship"))))
nb_done=0

for church in osm.find_relations(lambda x: (x.has_tag("amenity","place_of_worship")))+osm.find_ways(lambda x: (x.has_tag("amenity","place_of_worship"))):
	nb_done+=1
	print("Traitement de l'église :",nb_done,"/ ",nb_church,"id :",church.id)
	if isinstance(church,OsmWay):
		if church.is_closed: 
			initial_polygon_church=osm2shapely.osmWay2shapelyPolygon(church,osm)
		else: 
			print("Élément non traité : way trouvé non fermé mais représentant un batiment. way_id="+str(church.id))
			continue
	elif isinstance(church,OsmRelation):
		initial_polygon_church=osm2shapely.osmMultipolygonLargestOuter2shapelyPolygon(church,osm)
		if initial_polygon_church.is_empty: 
			print("Élément non traité : relation sans way outer fermé représentant un batiment. relation_id="+str(church.id))
			continue
	else: 
		raise ValueError("Élément non way non relation trouvé dans ways+relations. Element_id:"+str(church.id))
	
	polygon_church=initial_polygon_church
	
##méthode grossière pour rogner les extrémités et boursoufflures. Non obligatoire, semble améliorer le résultat en sortie, notamment en recentrant le centroid.
	try: 
		simplified_church=polygon_church.intersection(polygon_church.buffer(-7).buffer(8))
		if not simplified_church.area > polygon_church.area*0.7 or not isinstance(simplified_church,osm2shapely.shapely.geometry.Polygon): #simplified_church.is_empty is automatically rejected here.
			print("simplification de la géométrie échoué, utilisation de la géométrie initiale")
			simplified_church=polygon_church
	except:
		pass
	polygon_church=simplified_church
	if print_to_osm: osm2shapely.shapelyPolygon2osm_add_way(polygon_church,osm,[("simplified","yes")])

##Calcul du centroid de l'église
	centroid_church=polygon_church.buffer(-6).buffer(6).centroid #Supprime les couloirs sans issue
	if centroid_church.is_empty:
		centroid_church=polygon_church.buffer(-3).buffer(3).centroid
	if centroid_church.is_empty:
		centroid_church=polygon_church.centroid
	if centroid_church.is_empty:
		raise ValueError("centroid non calculable. objet="+str(church)+" et id="+str(church.id))
	
	centroid_node_id=osm2shapely.shapelyPoint2osm_add_node(centroid_church,osm,church.tags+[("centroid","yes")])
	church.set_tag("has_centroid","yes")
	
##Calcul du minimum_rotated_rectangle
	mrr=polygon_church.minimum_rotated_rectangle
	initial_church_in_mrr=mrr.intersection(initial_polygon_church)
	mrr_id=osm2shapely.shapelyPolygon2osm_add_way(mrr,osm,[("mrr","yes")])
	
##Recherche du transept
	wrap=lambda x: to_minimize(x,mrr,initial_church_in_mrr)
	t=differential_evolution(wrap,[(0.1,0.89),(0.11,0.9)],disp=True,callback=callback_differential_evolution,polish=True, maxiter=100,popsize=25)
	print(t)
	print(t.x)
	if t.x[0]<0 or t.x[1]>1 or t.x[0]>t.x[1]: raise ValueError("valeurs de minimisation hors 0-1")
	transept=make_sub_rectangle(mrr,t.x[0],t.x[1])
	if print_to_osm: transept_id=osm2shapely.shapelyPolygon2osm_add_way(transept,osm,[("transept","yes")])
	
##calcul des rectangles extérieurs au transept
	r1,r2=make_sub_rectangle(mrr,0,t.x[0]),make_sub_rectangle(mrr,t.x[1],1)

##calcul des points extérieurs au transept pour définir l'angle
	b1=make_sub_rectangle(mrr,0,0) #is LineString
	p1=b1.interpolate(0.5,normalized=True)
	p1_id=osm2shapely.shapelyPoint2osm_add_node(p1,osm,[("p1","yes")])
	
	b2=make_sub_rectangle(mrr,1,1) #is LineString
	p2=b2.interpolate(0.5,normalized=True)
	p2_id=osm2shapely.shapelyPoint2osm_add_node(p2,osm,[("p2","yes")])
	
	c1=r1.exterior.intersection(transept)
	c2=r2.exterior.intersection(transept)

##calcul des triangles non isocèles extérieurs au transept
	centroid_side1=initial_church_in_mrr.intersection(r1).centroid
	vertex1=b1.interpolate(b1.project(centroid_side1))
	t1=osm2shapely.shapely.geometry.collection.GeometryCollection([c1,vertex1]).convex_hull
	if print_to_osm: osm2shapely.shapelyPolygon2osm_add_way(t1,osm,[("t1","yes")])
	
	centroid_side2=initial_church_in_mrr.intersection(r2).centroid
	vertex2=b2.interpolate(b2.project(centroid_side2))
	t2=osm2shapely.shapely.geometry.collection.GeometryCollection([c2,vertex2]).convex_hull
	if print_to_osm: osm2shapely.shapelyPolygon2osm_add_way(t2,osm,[("t2","yes")])

	
##calcul des proportions de recouvrement
	area_int1=(initial_church_in_mrr.intersection(t1)).area
	area_tot1=initial_church_in_mrr.intersection(r1).area
	prop1=(area_tot1-area_int1)/area_int1
	area_int2=(initial_church_in_mrr.intersection(t2)).area
	area_tot2=initial_church_in_mrr.intersection(r2).area
	prop2=(area_tot2-area_int2)/area_int2
	
	print(prop1,prop2,prop1<prop2)
##calcul ds angles à partir des triangles	
	if prop1<prop2:
		triangles_angle=(-calcul_angle(osm.node(p1_id),osm.node(p2_id))+180)%360
	else:
		triangles_angle=(-calcul_angle(osm.node(p2_id),osm.node(p1_id))+180)%360

##Calcul des angles
	osm.nodes[centroid_node_id].set_tag("angle",str(round(triangles_angle)))
	#if print_to_osm: osm.save_xml_file(in_file.replace('.osm','')+"_post_temp.osm")

print('Enregistrement du fichier de sortie')
osm.save_xml_file(in_file.replace('.osm','')+"_post.osm")
print('OK')