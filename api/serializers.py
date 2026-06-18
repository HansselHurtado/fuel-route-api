from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200,
        help_text="Starting location within the USA (e.g. 'New York, NY')",
    )
    end = serializers.CharField(
        max_length=200,
        help_text="Destination within the USA (e.g. 'Los Angeles, CA')",
    )
