from osmdata import *
import sys
import osm2shapely
from add_angles import calcul_angle

try : in_file=sys.argv[1]
except: 
	print("Usage : python add_church_angle.py infile.osm")
	sys.exit()

print('Chargement du fichier : '+in_file)
osm = OsmData()
osm.load_xml_file(in_file)
osm.upload=False

print('Traitement des éléments')
for church in osm.find_ways(lambda x: (x.has_tag("amenity","place_of_worship")))+osm.find_relations(lambda x: (x.has_tag("amenity","place_of_worship"))):
	if isinstance(church,OsmWay):
		if church.is_closed: polygon_church=osm2shapely.osmWay2shapelyPolygon(church,osm)
		else: 
			print("way trouvé non fermé mais représentant un batiment. way_id="+str(church.id))
			continue
	elif isinstance(church,OsmRelation):
		polygon_church=osm2shapely.osmMultipolygonLargestOuter2shapelyPolygon(church,osm)
		if polygon_church.is_empty: 
			print("Relation sans way outer fermé représentant un batiment. relation_id="+str(church.id))
			continue
	else: 
		raise ValueError("Élément non way non relation trouvé dans ways+relations")
	
	try: #méthode grossière pour rogner les extrémités et boursoufflures. Non obligatoire, semble améliorer le résultat en sortie, notamment en recentrant le centroid.
		simplified_church=polygon_church.intersection(polygon_church.buffer(-7).buffer(8))
		if not simplified_church.is_empty: 
			polygon_church=simplified_church
			osm2shapely.shapelyPolygon2osm_add_way(polygon_church,osm,[("simplified","yes")])
	except:
		pass
	
	centroid_church=polygon_church.buffer(-6).buffer(6).centroid #Supprime les couloirs sans issue
	if centroid_church.is_empty:
		centroid_church=polygon_church.buffer(-3).buffer(3).centroid
	if centroid_church.is_empty:
		centroid_church=polygon_church.centroid
	if centroid_church.is_empty:
		raise ValueError("centroid non calculable. objet="+str(church)+" et id="+str(church.id))
	
	centroid_node_id=osm2shapely.shapelyPoint2osm_add_node(centroid_church,osm,church.tags+[("centroid","yes")])
	church.set_tag("has_centroid","yes")
	
	centroid_choir=polygon_church.buffer(-8).centroid
	if centroid_choir.is_empty:
		centroid_choir=polygon_church.buffer(-4).centroid
	if centroid_choir.is_empty:
		centroid_choir=polygon_church.buffer(-1).centroid
	if centroid_choir.is_empty:
		centroid_choir=osm2shapely.shapely.geometry.Point(centroid_church.x,centroid_church.y+1)
		print("Note : centroid du choeur absent (buffer=1 renvoie polygone vide) pour objet numéro"+str(church.id))
	choir_node_id=osm2shapely.shapelyPoint2osm_add_node(centroid_choir,osm,[("choir","yes")])
	
	distance_centroids=centroid_church.distance(centroid_choir)
	
##Calcul minimum_rotated_rectangle
	mrr=polygon_church.minimum_rotated_rectangle
	mrr_id=osm2shapely.shapelyPolygon2osm_add_way(mrr,osm,[("mrr","yes")])
##Trouver le long coté du mrr
	if osm2shapely.shapely.geometry.Point(mrr.exterior.coords[0]).distance(osm2shapely.shapely.geometry.Point(mrr.exterior.coords[1]))>osm2shapely.shapely.geometry.Point(mrr.exterior.coords[2]).distance(osm2shapely.shapely.geometry.Point(mrr.exterior.coords[1])): i=0
	else: i=1
##Calcul des angles
	mrr_angle=(-calcul_angle(osm.node(osm.ways[mrr_id].nodes[i]),osm.node(osm.ways[mrr_id].nodes[i+1])))%180
	del i
	centroids_angle=(-calcul_angle(osm.node(centroid_node_id),osm.node(choir_node_id)))%360
	osm.way(mrr_id).set_tag("angle",str(round(mrr_angle)))
	
	
	angle=mrr_angle
	if (distance_centroids>0.2) and (abs((mrr_angle-centroids_angle+90)%180 -90)<30): #Eglise selon le grand axe du mrr
		if not abs((mrr_angle-centroids_angle+180)%360 -180)<30:#direction inverse
			angle+=180

	osm.nodes[centroid_node_id].set_tag("angle",str(round(angle)))
	osm.nodes[centroid_node_id].set_tag("angle_centroid",str(round(centroids_angle)))

print('Enregistrement du fichier de sortie')
osm.save_xml_file(in_file.replace('.osm','')+"_post.osm")