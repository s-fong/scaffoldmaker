'''
Class for generating a shield-shaped mesh, with a regular flat top but
a rounded bottom formed by having two points where 3 square elements
merge to form a triangle.
'''
from __future__ import division
import copy
import math
from opencmiss.zinc.element import Element
from opencmiss.zinc.field import Field
from opencmiss.zinc.node import Node
from scaffoldmaker.utils import vector
from scaffoldmaker.utils.eftfactory_tricubichermite import eftfactory_tricubichermite
from scaffoldmaker.utils.eft_utils import remapEftNodeValueLabel, setEftScaleFactorIds
from scaffoldmaker.utils.interpolation import sampleCubicHermiteCurves
from scaffoldmaker.utils.tracksurface import TrackSurface, TrackSurfacePosition, calculate_surface_axes


class ShieldMesh:
    '''
    Shield mesh generator. Has one element through thickness.
    '''

    def __init__(self, elementsCountUp, elementsCountAcross, elementsCountRim, trackSurface : TrackSurface=None):
        '''
        :param trackSurface: Optional trackSurface to store or restrict points to.
        '''
        self.elementsCountUp = elementsCountUp
        self.elementsCountAcross = elementsCountAcross
        self.elementsCountRim = elementsCountRim
        self.elementsCountUpRegular = elementsCountUp - 2 - elementsCountRim
        self.elementsCountAcrossBottom = self.elementsCountAcross - 2*elementsCountRim
        self.elementsCountAroundFull = 2*self.elementsCountUpRegular + self.elementsCountAcrossBottom
        #self.elementsCountAroundHalf = self.elementsCountAroundFull//2
        self.trackSurface = trackSurface
        self.px  = [ [], [] ]
        self.pd1 = [ [], [] ]
        self.pd2 = [ [], [] ]
        self.pd3 = [ [], [] ]
        self.nodeId = [ [], [] ]
        for n3 in range(2):
            for n2 in range(elementsCountUp + 1):
                for p in [ self.px[n3], self.pd1[n3], self.pd2[n3], self.pd3[n3], self.nodeId[n3] ]:
                    p.append([ None ]*(elementsCountAcross + 1))
        if trackSurface:
            self.pProportions = [ [ None ]*(elementsCountAcross + 1) for n2 in range(elementsCountUp + 1) ]
        self.elementId = [ [ None ]*elementsCountAcross for n2 in range(elementsCountUp) ]


    def convertRimIndex(self, ix):
        '''
        Convert point index around the lower rim to n1, n2
        :param ix: index around from 0 to self.elementsCountAroundFull
        :return: n1, n2
        '''
        assert 0 <= ix <= self.elementsCountAroundFull
        if ix <= self.elementsCountUpRegular:
            return 0, self.elementsCountUp - ix
        rx = self.elementsCountAroundFull - ix
        if rx <= self.elementsCountUpRegular:
            return self.elementsCountAcross, self.elementsCountUp - rx
        return self.elementsCountRim + ix - self.elementsCountUpRegular, 0


    def getTriplePoints(self, n3):
        '''
        Compute coordinates and derivatives of points where 3 square elements merge.
        :param n3: Index of through-wall coordinates to use.
        '''
        # LV triple points
        n1a = self.elementsCountRim
        n1b = n1a + 1
        n1c = n1a + 2
        m1a = self.elementsCountAcross - self.elementsCountRim
        m1b = m1a - 1
        m1c = m1a - 2
        n2a = self.elementsCountRim
        n2b = n2a + 1
        n2c = n2a + 2
        # left
        ltx = []
        tx, td1 = sampleCubicHermiteCurves(
            [ self.px[n3][n2a][n1c], self.px[n3][n2c][n1b] ], [ [ (self.pd1[n3][n2a][n1c][c] + self.pd2[n3][n2a][n1c][c]) for c in range(3) ], self.pd2[n3][n2c][n1b] ], 2, arcLengthDerivatives = True)[0:2]
        ltx.append(tx[1])
        tx, td1 = sampleCubicHermiteCurves(
            [ self.px[n3][n2a][n1b], self.px[n3][n2c][n1c] ], [ self.pd1[n3][n2a][n1b], [ (self.pd1[n3][n2c][n1c][c] + self.pd2[n3][n2c][n1c][c]) for c in range(3) ] ], 2, arcLengthDerivatives = True)[0:2]
        ltx.append(tx[1])
        tx, td1 = sampleCubicHermiteCurves(
            [ self.px[n3][n2c][0], self.px[n3][n2b][n1c] ], [ [ (self.pd1[n3][n2c][0][c] - self.pd2[n3][n2c][0][c]) for c in range(3) ], self.pd1[n3][n2b][n1c] ], 2, arcLengthDerivatives = True)[0:2]
        ltx.append(tx[1])
        x = [ (ltx[0][c] + ltx[1][c] + ltx[2][c])/3.0 for c in range(3) ]
        if self.trackSurface:
            p = self.trackSurface.findNearestPosition(x, startPosition=self.trackSurface.createPositionProportion(*(self.pProportions[n2b][n1c])))
            self.pProportions[n2b][n1b] = self.trackSurface.getProportion(p)
            x, sd1, sd2 = self.trackSurface.evaluateCoordinates(p, derivatives=True)
            d1, d2, d3 = calculate_surface_axes(sd1, sd2, vector.normalise(sd1))
            self.pd3[n3][n2b][n1b] = d3
        self.px [n3][n2b][n1b] = x
        self.pd1[n3][n2b][n1b] = [ (self.px[n3][n2b][n1c][c] - self.px[n3][n2b][n1b][c]) for c in range(3) ]
        self.pd2[n3][n2b][n1b] = [ (self.px[n3][n2c][n1b][c] - self.px[n3][n2b][n1b][c]) for c in range(3) ]
        if not self.trackSurface:
            self.pd3[n3][n2b][n1b] = vector.normalise(vector.crossproduct3(self.pd1[n3][n2b][n1b], self.pd2[n3][n2b][n1b]))
        # right
        rtx = []
        tx, td1 = sampleCubicHermiteCurves(
            [ self.px[n3][n2a][m1c], self.px[n3][n2c][m1b] ], [ [ (-self.pd1[n3][n2a][m1c][c] + self.pd2[n3][n2a][m1c][c]) for c in range(3) ], self.pd2[n3][n2c][m1b] ], 2, arcLengthDerivatives = True)[0:2]
        rtx.append(tx[1])
        tx, td1 = sampleCubicHermiteCurves(
            [ self.px[n3][n2a][m1b], self.px[n3][n2c][m1c] ], [ [ -d for d in self.pd1[n3][n2a][m1b] ], [ (-self.pd1[n3][n2c][m1c][c] + self.pd2[n3][n2c][m1c][c]) for c in range(3) ] ], 2, arcLengthDerivatives = True)[0:2]
        rtx.append(tx[1])
        tx, td1 = sampleCubicHermiteCurves(
            [ self.px[n3][n2c][m1a], self.px[n3][n2b][m1c] ], [ [ (-self.pd1[n3][n2c][m1a][c] - self.pd2[n3][n2c][m1a][c]) for c in range(3) ], [ -d for d in self.pd1[n3][n2b][m1c] ] ], 2, arcLengthDerivatives = True)[0:2]
        rtx.append(tx[1])
        x = [ (rtx[0][c] + rtx[1][c] + rtx[2][c])/3.0 for c in range(3) ]
        if self.trackSurface:
            p = self.trackSurface.findNearestPosition(x, startPosition=self.trackSurface.createPositionProportion(*(self.pProportions[n2b][m1c])))
            self.pProportions[n2b][m1b] = self.trackSurface.getProportion(p)
            x, sd1, sd2 = self.trackSurface.evaluateCoordinates(p, derivatives=True)
            d1, d2, d3 = calculate_surface_axes(sd1, sd2, vector.normalise(sd1))
            self.pd3[n3][n2b][m1b] = d3
        self.px [n3][n2b][m1b] = x
        self.pd1[n3][n2b][m1b] = [ (self.px[n3][n2b][m1b][c] - self.px[n3][n2b][m1c][c]) for c in range(3) ]
        self.pd2[n3][n2b][m1b] = [ (self.px[n3][n2c][m1b][c] - self.px[n3][n2b][m1b][c]) for c in range(3) ]
        if not self.trackSurface:
            self.pd3[n3][n2b][m1b] = vector.normalise(vector.crossproduct3(self.pd1[n3][n2b][m1b], self.pd2[n3][n2b][m1b]))


    def generateNodes(self, fieldmodule, coordinates, startNodeIdentifier):
        """
        Create shield elements from nodes.
        :param fieldmodule: Zinc fieldmodule to create elements in.
        :param coordinates: Coordinate field to define.
        :param startElementIdentifier: First element identifier to use.
        :param meshGroups: Zinc mesh groups to add elements to.
        :return: next elementIdentifier, elementId[e2][e1].
         """
        nodeIdentifier = startNodeIdentifier
        nodes = fieldmodule.findNodesetByFieldDomainType(Field.DOMAIN_TYPE_NODES)
        nodetemplate = nodes.createNodetemplate()
        nodetemplate.defineField(coordinates)
        nodetemplate.setValueNumberOfVersions(coordinates, -1, Node.VALUE_LABEL_VALUE, 1)
        nodetemplate.setValueNumberOfVersions(coordinates, -1, Node.VALUE_LABEL_D_DS1, 1)
        nodetemplate.setValueNumberOfVersions(coordinates, -1, Node.VALUE_LABEL_D_DS2, 1)
        nodetemplate.setValueNumberOfVersions(coordinates, -1, Node.VALUE_LABEL_D_DS3, 1)
        cache = fieldmodule.createFieldcache()

        if False:
            for n2 in range(self.elementsCountUp, -1, -1):
                s = ""
                for n1 in range(self.elementsCountAcross + 1):
                    s += str(n1) if self.px[1][n2][n1] else " "
                print(n2, s, n2 - self.elementsCountUp - 1)

        for n2 in range(self.elementsCountUp + 1):
            for n3 in range(2):
                for n1 in range(self.elementsCountAcross + 1):
                    if self.px[n3][n2][n1]:
                        node = nodes.createNode(nodeIdentifier, nodetemplate)
                        self.nodeId[n3][n2][n1] = nodeIdentifier
                        cache.setNode(node)
                        coordinates.setNodeParameters(cache, -1, Node.VALUE_LABEL_VALUE, 1, self.px [n3][n2][n1])
                        if self.pd1[n3][n2][n1]:  # GRC temp
                            coordinates.setNodeParameters(cache, -1, Node.VALUE_LABEL_D_DS1, 1, self.pd1[n3][n2][n1])
                        if self.pd2[n3][n2][n1]:  # GRC temp
                            coordinates.setNodeParameters(cache, -1, Node.VALUE_LABEL_D_DS2, 1, self.pd2[n3][n2][n1])
                        if self.pd3[n3][n2][n1]:  # GRC temp
                            coordinates.setNodeParameters(cache, -1, Node.VALUE_LABEL_D_DS3, 1, self.pd3[n3][n2][n1])
                        nodeIdentifier += 1

        return nodeIdentifier


    def generateElements(self, fieldmodule, coordinates, startElementIdentifier, meshGroups=[]):
        """
        Create shield elements from nodes.
        :param fieldmodule: Zinc fieldmodule to create elements in.
        :param coordinates: Coordinate field to define.
        :param startElementIdentifier: First element identifier to use.
        :param meshGroups: Zinc mesh groups to add elements to.
        :return: next elementIdentifier.
         """
        elementIdentifier = startElementIdentifier
        elementId = []
        useCrossDerivatives = False
        mesh = fieldmodule.findMeshByDimension(3)

        tricubichermite = eftfactory_tricubichermite(mesh, useCrossDerivatives)
        eft = tricubichermite.createEftNoCrossDerivatives()
        elementtemplate = mesh.createElementtemplate()
        elementtemplate.setElementShapeType(Element.SHAPE_TYPE_CUBE)
        elementtemplate.defineField(coordinates, -1, eft)

        elementtemplate1 = mesh.createElementtemplate()
        elementtemplate1.setElementShapeType(Element.SHAPE_TYPE_CUBE)

        isEven = (self.elementsCountAcross % 2) == 0
        elementsCountAcrossPlusOneHalf = (self.elementsCountAcross + 1)//2
        e1a = self.elementsCountRim
        e1b = e1a + 1
        e1z = self.elementsCountAcross - 1 - self.elementsCountRim
        e1y = e1z - 1
        e2a = self.elementsCountRim
        e2b = self.elementsCountRim + 1
        e2c = self.elementsCountRim + 2
        for e2 in range(self.elementsCountUp):
            for e1 in range(self.elementsCountAcross):
                eft1 = eft
                scalefactors = None
                nids = [ self.nodeId[0][e2][e1], self.nodeId[0][e2][e1 + 1], self.nodeId[0][e2 + 1][e1], self.nodeId[0][e2 + 1][e1 + 1], 
                         self.nodeId[1][e2][e1], self.nodeId[1][e2][e1 + 1], self.nodeId[1][e2 + 1][e1], self.nodeId[1][e2 + 1][e1 + 1] ]
                if e2 < e2b:
                    if (e1 < e1b) or (e1 > e1y):
                        continue
                    if e2 < e2a:
                        if e1 < elementsCountAcrossPlusOneHalf:
                            nids = [ nids[1], nids[3], nids[0], nids[2], nids[5], nids[7], nids[4], nids[6] ]
                        else:
                            nids = [ nids[2], nids[0], nids[3], nids[1], nids[6], nids[4], nids[7], nids[5] ]
                    else:
                        eft1 = tricubichermite.createEftNoCrossDerivatives()
                        setEftScaleFactorIds(eft1, [1], [])
                        scalefactors = [ -1.0 ]
                        if e1 < elementsCountAcrossPlusOneHalf:
                            if e1 < (elementsCountAcrossPlusOneHalf - 1):
                                remapEftNodeValueLabel(eft1, [ 1, 2, 5, 6 ], Node.VALUE_LABEL_D_DS1, [ ( Node.VALUE_LABEL_D_DS2, [1] ) ])
                                remapEftNodeValueLabel(eft1, [ 1, 2, 5, 6 ], Node.VALUE_LABEL_D_DS2, [ ( Node.VALUE_LABEL_D_DS1, [] ) ])
                            else:
                                remapEftNodeValueLabel(eft1, [ 1, 5 ], Node.VALUE_LABEL_D_DS1, [ ( Node.VALUE_LABEL_D_DS2, [1] ) ])
                                remapEftNodeValueLabel(eft1, [ 1, 5 ], Node.VALUE_LABEL_D_DS2, [ ( Node.VALUE_LABEL_D_DS1, [] ) ])
                        if e1 >= elementsCountAcrossPlusOneHalf:
                            if e1 > elementsCountAcrossPlusOneHalf:
                                remapEftNodeValueLabel(eft1, [ 1, 2, 5, 6 ], Node.VALUE_LABEL_D_DS2, [ ( Node.VALUE_LABEL_D_DS1, [1] ) ])
                                remapEftNodeValueLabel(eft1, [ 1, 2, 5, 6 ], Node.VALUE_LABEL_D_DS1, [ ( Node.VALUE_LABEL_D_DS2, [] ) ])
                            else:
                                remapEftNodeValueLabel(eft1, [ 2, 6 ], Node.VALUE_LABEL_D_DS2, [ ( Node.VALUE_LABEL_D_DS1, [1] ) ])
                                remapEftNodeValueLabel(eft1, [ 2, 6 ], Node.VALUE_LABEL_D_DS1, [ ( Node.VALUE_LABEL_D_DS2, [] ) ])
                        if e1 == e1b:
                            remapEftNodeValueLabel(eft1, [ 3, 7 ], Node.VALUE_LABEL_D_DS2, [ ( Node.VALUE_LABEL_D_DS1, [] ), ( Node.VALUE_LABEL_D_DS2, [] ) ])
                        if e1 == e1y:
                            remapEftNodeValueLabel(eft1, [ 4, 8 ], Node.VALUE_LABEL_D_DS2, [ ( Node.VALUE_LABEL_D_DS1, [1] ), ( Node.VALUE_LABEL_D_DS2, [] ) ])
                elif e2 == e2b:
                    if e1 < e1a:
                        e2r = e1
                        nids[0] = self.nodeId[0][e2r    ][e1b]
                        nids[1] = self.nodeId[0][e2r + 1][e1b]
                        nids[4] = self.nodeId[1][e2r    ][e1b]
                        nids[5] = self.nodeId[1][e2r + 1][e1b]
                    elif e1 == e1a:
                        nids[0] = self.nodeId[0][e2a][e1b]
                        nids[4] = self.nodeId[1][e2a][e1b]
                        eft1 = tricubichermite.createEftNoCrossDerivatives()
                        setEftScaleFactorIds(eft1, [1], [])
                        scalefactors = [ -1.0 ]
                        remapEftNodeValueLabel(eft1, [ 2, 6 ], Node.VALUE_LABEL_D_DS1, [ ( Node.VALUE_LABEL_D_DS1, [] ), ( Node.VALUE_LABEL_D_DS2, [] ) ])
                    elif e1 == e1z:
                        nids[1] = self.nodeId[0][e2a][e1z]
                        nids[5] = self.nodeId[1][e2a][e1z]
                        eft1 = tricubichermite.createEftNoCrossDerivatives()
                        setEftScaleFactorIds(eft1, [1], [])
                        scalefactors = [ -1.0 ]
                        remapEftNodeValueLabel(eft1, [ 1, 5 ], Node.VALUE_LABEL_D_DS1, [ ( Node.VALUE_LABEL_D_DS1, [] ), ( Node.VALUE_LABEL_D_DS2, [1] ) ])
                    elif e1 > e1z:
                        e2r = self.elementsCountAcross - e1
                        nids[0] = self.nodeId[0][e2r    ][e1z]
                        nids[1] = self.nodeId[0][e2r - 1][e1z]
                        nids[4] = self.nodeId[1][e2r    ][e1z]
                        nids[5] = self.nodeId[1][e2r - 1][e1z]
                if None in nids:
                    continue  # GRC temporary
                if eft1 is not eft:
                    elementtemplate1.defineField(coordinates, -1, eft1)
                    element = mesh.createElement(elementIdentifier, elementtemplate1)
                else:
                    element = mesh.createElement(elementIdentifier, elementtemplate)
                result2 = element.setNodesByIdentifier(eft1, nids)
                if scalefactors:
                    result3 = element.setScaleFactors(eft1, scalefactors)
                else:
                    result3 = 7
                #print('create element shield', elementIdentifier, result2, result3, nids)
                self.elementId[e2][e1] = elementIdentifier
                elementIdentifier += 1

                for meshGroup in meshGroups:
                    meshGroup.addElement(element)

        return elementIdentifier
