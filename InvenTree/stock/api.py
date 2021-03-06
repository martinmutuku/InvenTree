from django_filters.rest_framework import FilterSet, DjangoFilterBackend
from django_filters import NumberFilter

from rest_framework import generics, permissions, response, filters

from django.conf.urls import url, include

# from InvenTree.models import FilterChildren
from .models import StockLocation, StockItem
from .models import StockItemTracking

from .serializers import StockItemSerializer, StockQuantitySerializer
from .serializers import LocationSerializer
from .serializers import StockTrackingSerializer

from InvenTree.views import TreeSerializer
from InvenTree.serializers import DraftRUDView

from rest_framework.serializers import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions
from django.contrib.auth.models import User

class StockCategoryTree(TreeSerializer):
    title = 'Stock'
    model = StockLocation


class StockDetail(DraftRUDView):
    """

    get:
    Return a single StockItem object

    post:
    Update a StockItem

    delete:
    Remove a StockItem
    """

    queryset = StockItem.objects.all()
    serializer_class = StockItemSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)


class StockFilter(FilterSet):
    min_stock = NumberFilter(name='quantity', lookup_expr='gte')
    max_stock = NumberFilter(name='quantity', lookup_expr='lte')

    class Meta:
        model = StockItem
        fields = ['quantity', 'part', 'location']


class StockStocktake(APIView):
    """
    Stocktake API endpoint provides stock update of multiple items simultaneously
    The 'action' field tells the type of stock action to perform:
        * 'stocktake' - Count the stock item(s)
        * 'remove' - Remove the quantity provided from stock
        * 'add' - Add the quantity provided from stock
    """

    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]

    def post(self, request, *args, **kwargs):

        if not 'action' in request.data:
            raise ValidationError({'action': 'Stocktake action must be provided'})

        action = request.data['action']

        ACTIONS = ['stocktake', 'remove', 'add']

        if not action in ACTIONS:
            raise ValidationError({'action': 'Action must be one of ' + ','.join(ACTIONS)})

        if not 'items[]' in request.data:
            raise ValidationError({'items[]:' 'Request must contain list of items'})

        items = []

        # Ensure each entry is valid
        for entry in request.data['items[]']:
            if not 'pk' in entry:
                raise ValidationError({'pk': 'Each entry must contain pk field'})
            if not 'quantity' in entry:
                raise ValidationError({'quantity': 'Each entry must contain quantity field'})

            item = {}
            try:
                item['item'] = StockItem.objects.get(pk=entry['pk'])
            except StockItem.DoesNotExist:
                raise ValidationError({'pk': 'No matching StockItem found for pk={pk}'.format(pk=entry['pk'])})
            try:
                item['quantity'] = int(entry['quantity'])
            except ValueError:
                raise ValidationError({'quantity': 'Quantity must be an integer'})

            if item['quantity'] < 0:
                raise ValidationError({'quantity': 'Quantity must be >= 0'})

            items.append(item)

        # Stocktake notes
        notes = ''

        if 'notes' in request.data:
            notes = request.data['notes']


        for item in items:
            quantity = int(item['quantity'])

            if action == u'stocktake':
                item['item'].stocktake(quantity, request.user, notes=notes)
            elif action == u'remove':
                item['item'].take_stock(quantity, request.user, notes=notes)
            elif action == u'add':
                item['item'].add_stock(quantity, request.user, notes=notes)

        return Response({'success': 'success'})


class StockMove(APIView):

    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]

    def post(self, request, *args, **kwargs):

        data = request.data

        if not u'location' in data:
            raise ValidationError({'location': 'Destination must be specified'})

        loc_id = data.get(u'location')

        try:
            location = StockLocation.objects.get(pk=loc_id)
        except StockLocation.DoesNotExist:
            raise ValidationError({'location': 'Location does not exist'})

        if not u'parts[]' in data:
            raise ValidationError({'parts[]': 'Parts list must be specified'})

        part_list = data.get(u'parts[]')

        parts = []

        errors = []

        for pid in part_list:
            try:
                part = StockItem.objects.get(pk=pid)
                parts.append(part)
            except StockItem.DoesNotExist:
                errors.append({'part': 'Part {id} does not exist'.format(id=part_id)})

        if len(errors) > 0:
            raise ValidationError(errors)

        for part in parts:
            part.move(location, request.user)

        return Response({'success': 'Moved {n} parts to {loc}'.format(
            n=len(parts),
            loc=location.name
        )})


class StockLocationList(generics.ListCreateAPIView):

    queryset = StockLocation.objects.all()

    serializer_class = LocationSerializer

    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filter_fields = [
        'parent',
    ]


class StockList(generics.ListCreateAPIView):
    """

    get:
    Return a list of all StockItem objects
    (with optional query filters)

    post:
    Create a new StockItem
    """

    queryset = StockItem.objects.all()

    serializer_class = StockItemSerializer

    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filter_fields = [
        'part',
        'location',
        'supplier_part',
        'customer',
        'belongs_to',
        'status',
    ]


class StockStocktakeEndpoint(generics.UpdateAPIView):

    queryset = StockItem.objects.all()
    serializer_class = StockQuantitySerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)

    def update(self, request, *args, **kwargs):
        object = self.get_object()
        object.stocktake(request.data['quantity'], request.user)

        serializer = self.get_serializer(object)

        return response.Response(serializer.data)


class StockTrackingList(generics.ListCreateAPIView):

    queryset = StockItemTracking.objects.all()
    serializer_class = StockTrackingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly,]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filter_fields = [
        'item',
        'user',
    ]

    ordering = '-date'

    ordering_fields = [
        'date',
    ]

    search_fields = [
        'title',
        'notes',
    ]



class LocationDetail(generics.RetrieveUpdateDestroyAPIView):
    """

    get:
    Return a single StockLocation object

    post:
    Update a StockLocation object

    delete:
    Remove a StockLocation object

    """

    queryset = StockLocation.objects.all()
    serializer_class = LocationSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)


stock_endpoints = [
    url(r'^$', StockDetail.as_view(), name='stockitem-detail'),
]

location_endpoints = [
    url(r'^$', LocationDetail.as_view(), name='stocklocation-detail'),
]


stock_api_urls = [
    # Detail for a single stock item
    url(r'^(?P<pk>[0-9]+)/', include(stock_endpoints)),

    url(r'location/?', StockLocationList.as_view(), name='api-location-list'),

    url(r'location/(?P<pk>\d+)/', include(location_endpoints)),

    url(r'stocktake/?', StockStocktake.as_view(), name='api-stock-stocktake'),

    url(r'move/?', StockMove.as_view(), name='api-stock-move'),

    url(r'track/?', StockTrackingList.as_view(), name='api-stock-track'),

    url(r'^tree/?', StockCategoryTree.as_view(), name='api-stock-tree'),

    url(r'^.*$', StockList.as_view(), name='api-stock-list'),
]