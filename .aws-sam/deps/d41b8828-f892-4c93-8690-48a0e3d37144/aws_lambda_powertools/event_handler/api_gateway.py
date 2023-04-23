import base64
import json
import logging
import re
import traceback
import warnings
import zlib
from abc import ABC, abstractmethod
from enum import Enum
from functools import partial
from http import HTTPStatus
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Match,
    Optional,
    Pattern,
    Set,
    Tuple,
    Type,
    Union,
)

from aws_lambda_powertools.event_handler import content_types
from aws_lambda_powertools.event_handler.exceptions import NotFoundError, ServiceError
from aws_lambda_powertools.shared.cookies import Cookie
from aws_lambda_powertools.shared.functions import powertools_dev_is_set
from aws_lambda_powertools.shared.json_encoder import Encoder
from aws_lambda_powertools.utilities.data_classes import (
    ALBEvent,
    APIGatewayProxyEvent,
    APIGatewayProxyEventV2,
    LambdaFunctionUrlEvent,
)
from aws_lambda_powertools.utilities.data_classes.common import BaseProxyEvent
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = logging.getLogger(__name__)

_DYNAMIC_ROUTE_PATTERN = r"(<\w+>)"
_SAFE_URI = "-._~()'!*:@,;="  # https://www.ietf.org/rfc/rfc3986.txt
# API GW/ALB decode non-safe URI chars; we must support them too
_UNSAFE_URI = "%<> \[\]{}|^"  # noqa: W605
_NAMED_GROUP_BOUNDARY_PATTERN = rf"(?P\1[{_SAFE_URI}{_UNSAFE_URI}\\w]+)"
_ROUTE_REGEX = "^{}$"


class ProxyEventType(Enum):
    """An enumerations of the supported proxy event types."""

    APIGatewayProxyEvent = "APIGatewayProxyEvent"
    APIGatewayProxyEventV2 = "APIGatewayProxyEventV2"
    ALBEvent = "ALBEvent"
    LambdaFunctionUrlEvent = "LambdaFunctionUrlEvent"


class CORSConfig:
    """CORS Config

    Examples
    --------

    Simple cors example using the default permissive cors, not this should only be used during early prototyping

    ```python
    from aws_lambda_powertools.event_handler import APIGatewayRestResolver

    app = APIGatewayRestResolver()

    @app.get("/my/path", cors=True)
    def with_cors():
        return {"message": "Foo"}
    ```

    Using a custom CORSConfig where `with_cors` used the custom provided CORSConfig and `without_cors`
    do not include any cors headers.

    ```python
    from aws_lambda_powertools.event_handler.api_gateway import (
        APIGatewayRestResolver, CORSConfig
    )

    cors_config = CORSConfig(
        allow_origin="https://wwww.example.com/",
        expose_headers=["x-exposed-response-header"],
        allow_headers=["x-custom-request-header"],
        max_age=100,
        allow_credentials=True,
    )
    app = APIGatewayRestResolver(cors=cors_config)

    @app.get("/my/path")
    def with_cors():
        return {"message": "Foo"}

    @app.get("/another-one", cors=False)
    def without_cors():
        return {"message": "Foo"}
    ```
    """

    _REQUIRED_HEADERS = ["Authorization", "Content-Type", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"]

    def __init__(
        self,
        allow_origin: str = "*",
        allow_headers: Optional[List[str]] = None,
        expose_headers: Optional[List[str]] = None,
        max_age: Optional[int] = None,
        allow_credentials: bool = False,
    ):
        """
        Parameters
        ----------
        allow_origin: str
            The value of the `Access-Control-Allow-Origin` to send in the response. Defaults to "*", but should
            only be used during development.
        allow_headers: Optional[List[str]]
            The list of additional allowed headers. This list is added to list of
            built-in allowed headers: `Authorization`, `Content-Type`, `X-Amz-Date`,
            `X-Api-Key`, `X-Amz-Security-Token`.
        expose_headers: Optional[List[str]]
            A list of values to return for the Access-Control-Expose-Headers
        max_age: Optional[int]
            The value for the `Access-Control-Max-Age`
        allow_credentials: bool
            A boolean value that sets the value of `Access-Control-Allow-Credentials`
        """
        self.allow_origin = allow_origin
        self.allow_headers = set(self._REQUIRED_HEADERS + (allow_headers or []))
        self.expose_headers = expose_headers or []
        self.max_age = max_age
        self.allow_credentials = allow_credentials

    def to_dict(self) -> Dict[str, str]:
        """Builds the configured Access-Control http headers"""
        headers: Dict[str, str] = {
            "Access-Control-Allow-Origin": self.allow_origin,
            "Access-Control-Allow-Headers": ",".join(sorted(self.allow_headers)),
        }

        if self.expose_headers:
            headers["Access-Control-Expose-Headers"] = ",".join(self.expose_headers)
        if self.max_age is not None:
            headers["Access-Control-Max-Age"] = str(self.max_age)
        if self.allow_credentials is True:
            headers["Access-Control-Allow-Credentials"] = "true"
        return headers


class Response:
    """Response data class that provides greater control over what is returned from the proxy event"""

    def __init__(
        self,
        status_code: int,
        content_type: Optional[str] = None,
        body: Union[str, bytes, None] = None,
        headers: Optional[Dict[str, Union[str, List[str]]]] = None,
        cookies: Optional[List[Cookie]] = None,
    ):
        """

        Parameters
        ----------
        status_code: int
            Http status code, example 200
        content_type: str
            Optionally set the Content-Type header, example "application/json". Note this will be merged into any
            provided http headers
        body: Union[str, bytes, None]
            Optionally set the response body. Note: bytes body will be automatically base64 encoded
        headers: dict[str, Union[str, List[str]]]
            Optionally set specific http headers. Setting "Content-Type" here would override the `content_type` value.
        cookies: list[Cookie]
            Optionally set cookies.
        """
        self.status_code = status_code
        self.body = body
        self.base64_encoded = False
        self.headers: Dict[str, Union[str, List[str]]] = headers if headers else {}
        self.cookies = cookies or []
        if content_type:
            self.headers.setdefault("Content-Type", content_type)


class Route:
    """Internally used Route Configuration"""

    def __init__(
        self, method: str, rule: Pattern, func: Callable, cors: bool, compress: bool, cache_control: Optional[str]
    ):
        self.method = method.upper()
        self.rule = rule
        self.func = func
        self.cors = cors
        self.compress = compress
        self.cache_control = cache_control


class ResponseBuilder:
    """Internally used Response builder"""

    def __init__(self, response: Response, route: Optional[Route] = None):
        self.response = response
        self.route = route

    def _add_cors(self, cors: CORSConfig):
        """Update headers to include the configured Access-Control headers"""
        self.response.headers.update(cors.to_dict())

    def _add_cache_control(self, cache_control: str):
        """Set the specified cache control headers for 200 http responses. For non-200 `no-cache` is used."""
        cache_control = cache_control if self.response.status_code == 200 else "no-cache"
        self.response.headers["Cache-Control"] = cache_control

    def _compress(self):
        """Compress the response body, but only if `Accept-Encoding` headers includes gzip."""
        self.response.headers["Content-Encoding"] = "gzip"
        if isinstance(self.response.body, str):
            logger.debug("Converting string response to bytes before compressing it")
            self.response.body = bytes(self.response.body, "utf-8")
        gzip = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
        self.response.body = gzip.compress(self.response.body) + gzip.flush()

    def _route(self, event: BaseProxyEvent, cors: Optional[CORSConfig]):
        """Optionally handle any of the route's configure response handling"""
        if self.route is None:
            return
        if self.route.cors:
            self._add_cors(cors or CORSConfig())
        if self.route.cache_control:
            self._add_cache_control(self.route.cache_control)
        if self.route.compress and "gzip" in (event.get_header_value("accept-encoding", "") or ""):
            self._compress()

    def build(self, event: BaseProxyEvent, cors: Optional[CORSConfig] = None) -> Dict[str, Any]:
        """Build the full response dict to be returned by the lambda"""
        self._route(event, cors)

        if isinstance(self.response.body, bytes):
            logger.debug("Encoding bytes response with base64")
            self.response.base64_encoded = True
            self.response.body = base64.b64encode(self.response.body).decode()

        return {
            "statusCode": self.response.status_code,
            "body": self.response.body,
            "isBase64Encoded": self.response.base64_encoded,
            **event.header_serializer().serialize(headers=self.response.headers, cookies=self.response.cookies),
        }


class BaseRouter(ABC):
    current_event: BaseProxyEvent
    lambda_context: LambdaContext
    context: dict

    @abstractmethod
    def route(
        self,
        rule: str,
        method: Any,
        cors: Optional[bool] = None,
        compress: bool = False,
        cache_control: Optional[str] = None,
    ):
        raise NotImplementedError()

    def get(self, rule: str, cors: Optional[bool] = None, compress: bool = False, cache_control: Optional[str] = None):
        """Get route decorator with GET `method`

        Examples
        --------
        Simple example with a custom lambda handler using the Tracer capture_lambda_handler decorator

        ```python
        from aws_lambda_powertools import Tracer
        from aws_lambda_powertools.event_handler import APIGatewayRestResolver

        tracer = Tracer()
        app = APIGatewayRestResolver()

        @app.get("/get-call")
        def simple_get():
            return {"message": "Foo"}

        @tracer.capture_lambda_handler
        def lambda_handler(event, context):
            return app.resolve(event, context)
        ```
        """
        return self.route(rule, "GET", cors, compress, cache_control)

    def post(self, rule: str, cors: Optional[bool] = None, compress: bool = False, cache_control: Optional[str] = None):
        """Post route decorator with POST `method`

        Examples
        --------
        Simple example with a custom lambda handler using the Tracer capture_lambda_handler decorator

        ```python
        from aws_lambda_powertools import Tracer
        from aws_lambda_powertools.event_handler import APIGatewayRestResolver

        tracer = Tracer()
        app = APIGatewayRestResolver()

        @app.post("/post-call")
        def simple_post():
            post_data: dict = app.current_event.json_body
            return {"message": post_data["value"]}

        @tracer.capture_lambda_handler
        def lambda_handler(event, context):
            return app.resolve(event, context)
        ```
        """
        return self.route(rule, "POST", cors, compress, cache_control)

    def put(self, rule: str, cors: Optional[bool] = None, compress: bool = False, cache_control: Optional[str] = None):
        """Put route decorator with PUT `method`

        Examples
        --------
        Simple example with a custom lambda handler using the Tracer capture_lambda_handler decorator

        ```python
        from aws_lambda_powertools import Tracer
        from aws_lambda_powertools.event_handler import APIGatewayRestResolver

        tracer = Tracer()
        app = APIGatewayRestResolver()

        @app.put("/put-call")
        def simple_put():
            put_data: dict = app.current_event.json_body
            return {"message": put_data["value"]}

        @tracer.capture_lambda_handler
        def lambda_handler(event, context):
            return app.resolve(event, context)
        ```
        """
        return self.route(rule, "PUT", cors, compress, cache_control)

    def delete(
        self, rule: str, cors: Optional[bool] = None, compress: bool = False, cache_control: Optional[str] = None
    ):
        """Delete route decorator with DELETE `method`

        Examples
        --------
        Simple example with a custom lambda handler using the Tracer capture_lambda_handler decorator

        ```python
        from aws_lambda_powertools import Tracer
        from aws_lambda_powertools.event_handler import APIGatewayRestResolver

        tracer = Tracer()
        app = APIGatewayRestResolver()

        @app.delete("/delete-call")
        def simple_delete():
            return {"message": "deleted"}

        @tracer.capture_lambda_handler
        def lambda_handler(event, context):
            return app.resolve(event, context)
        ```
        """
        return self.route(rule, "DELETE", cors, compress, cache_control)

    def patch(
        self, rule: str, cors: Optional[bool] = None, compress: bool = False, cache_control: Optional[str] = None
    ):
        """Patch route decorator with PATCH `method`

        Examples
        --------
        Simple example with a custom lambda handler using the Tracer capture_lambda_handler decorator

        ```python
        from aws_lambda_powertools import Tracer
        from aws_lambda_powertools.event_handler import APIGatewayRestResolver

        tracer = Tracer()
        app = APIGatewayRestResolver()

        @app.patch("/patch-call")
        def simple_patch():
            patch_data: dict = app.current_event.json_body
            patch_data["value"] = patched

            return {"message": patch_data}

        @tracer.capture_lambda_handler
        def lambda_handler(event, context):
            return app.resolve(event, context)
        ```
        """
        return self.route(rule, "PATCH", cors, compress, cache_control)

    def append_context(self, **additional_context):
        """Append key=value data as routing context"""
        self.context.update(**additional_context)

    def clear_context(self):
        """Resets routing context"""
        self.context.clear()


class ApiGatewayResolver(BaseRouter):
    """API Gateway and ALB proxy resolver

    Examples
    --------
    Simple example with a custom lambda handler using the Tracer capture_lambda_handler decorator

    ```python
    from aws_lambda_powertools import Tracer
    from aws_lambda_powertools.event_handler import APIGatewayRestResolver

    tracer = Tracer()
    app = APIGatewayRestResolver()

    @app.get("/get-call")
    def simple_get():
        return {"message": "Foo"}

    @app.post("/post-call")
    def simple_post():
        post_data: dict = app.current_event.json_body
        return {"message": post_data["value"]}

    @tracer.capture_lambda_handler
    def lambda_handler(event, context):
        return app.resolve(event, context)
    ```
    """

    def __init__(
        self,
        proxy_type: Enum = ProxyEventType.APIGatewayProxyEvent,
        cors: Optional[CORSConfig] = None,
        debug: Optional[bool] = None,
        serializer: Optional[Callable[[Dict], str]] = None,
        strip_prefixes: Optional[List[str]] = None,
    ):
        """
        Parameters
        ----------
        proxy_type: ProxyEventType
            Proxy request type, defaults to API Gateway V1
        cors: CORSConfig
            Optionally configure and enabled CORS. Not each route will need to have to cors=True
        debug: Optional[bool]
            Enables debug mode, by default False. Can be also be enabled by "POWERTOOLS_DEV"
            environment variable
        serializer : Callable, optional
            function to serialize `obj` to a JSON formatted `str`, by default json.dumps
        strip_prefixes: List[str], optional
            optional list of prefixes to be removed from the request path before doing the routing. This is often used
            with api gateways with multiple custom mappings.
        """
        self._proxy_type = proxy_type
        self._routes: List[Route] = []
        self._route_keys: List[str] = []
        self._exception_handlers: Dict[Type, Callable] = {}
        self._cors = cors
        self._cors_enabled: bool = cors is not None
        self._cors_methods: Set[str] = {"OPTIONS"}
        self._debug = self._has_debug(debug)
        self._strip_prefixes = strip_prefixes
        self.context: Dict = {}  # early init as customers might add context before event resolution

        # Allow for a custom serializer or a concise json serialization
        self._serializer = serializer or partial(json.dumps, separators=(",", ":"), cls=Encoder)

    def route(
        self,
        rule: str,
        method: Union[str, Union[List[str], Tuple[str]]],
        cors: Optional[bool] = None,
        compress: bool = False,
        cache_control: Optional[str] = None,
    ):
        """Route decorator includes parameter `method`"""

        def register_resolver(func: Callable):
            methods = (method,) if isinstance(method, str) else method
            logger.debug(f"Adding route using rule {rule} and methods: {','.join((m.upper() for m in methods))}")
            if cors is None:
                cors_enabled = self._cors_enabled
            else:
                cors_enabled = cors

            for item in methods:
                self._routes.append(Route(item, self._compile_regex(rule), func, cors_enabled, compress, cache_control))
                route_key = item + rule
                if route_key in self._route_keys:
                    warnings.warn(
                        f"A route like this was already registered. method: '{item}' rule: '{rule}'", stacklevel=2
                    )
                self._route_keys.append(route_key)
                if cors_enabled:
                    logger.debug(f"Registering method {item.upper()} to Allow Methods in CORS")
                    self._cors_methods.add(item.upper())
            return func

        return register_resolver

    def resolve(self, event, context) -> Dict[str, Any]:
        """Resolves the response based on the provide event and decorator routes

        Parameters
        ----------
        event: Dict[str, Any]
            Event
        context: LambdaContext
            Lambda context
        Returns
        -------
        dict
            Returns the dict response
        """
        if isinstance(event, BaseProxyEvent):
            warnings.warn(
                "You don't need to serialize event to Event Source Data Class when using Event Handler; "
                "see issue #1152",
                stacklevel=2,
            )
            event = event.raw_event

        if self._debug:
            print(self._json_dump(event))

        # Populate router(s) dependencies without keeping a reference to each registered router
        BaseRouter.current_event = self._to_proxy_event(event)
        BaseRouter.lambda_context = context

        response = self._resolve().build(self.current_event, self._cors)
        self.clear_context()
        return response

    def __call__(self, event, context) -> Any:
        return self.resolve(event, context)

    @staticmethod
    def _has_debug(debug: Optional[bool] = None) -> bool:
        # It might have been explicitly switched off (debug=False)
        if debug is not None:
            return debug

        return powertools_dev_is_set()

    @staticmethod
    def _compile_regex(rule: str, base_regex: str = _ROUTE_REGEX):
        """Precompile regex pattern

        Logic
        -----

        1. Find any dynamic routes defined as <pattern>
            e.g. @app.get("/accounts/<account_id>")
        2. Create a new regex by substituting every dynamic route found as a named group (?P<group>),
        and match whole words only (word boundary) instead of a greedy match

            non-greedy example with word boundary

                rule: '/accounts/<account_id>'
                regex: r'/accounts/(?P<account_id>\\w+\\b)'

                value: /accounts/123/some_other_path
                account_id: 123

            greedy example without word boundary

                regex: r'/accounts/(?P<account_id>.+)'

                value: /accounts/123/some_other_path
                account_id: 123/some_other_path
        3. Compiles a regex and include start (^) and end ($) in between for an exact match

        NOTE: See #520 for context
        """
        rule_regex: str = re.sub(_DYNAMIC_ROUTE_PATTERN, _NAMED_GROUP_BOUNDARY_PATTERN, rule)
        return re.compile(base_regex.format(rule_regex))

    def _to_proxy_event(self, event: Dict) -> BaseProxyEvent:
        """Convert the event dict to the corresponding data class"""
        if self._proxy_type == ProxyEventType.APIGatewayProxyEvent:
            logger.debug("Converting event to API Gateway REST API contract")
            return APIGatewayProxyEvent(event)
        if self._proxy_type == ProxyEventType.APIGatewayProxyEventV2:
            logger.debug("Converting event to API Gateway HTTP API contract")
            return APIGatewayProxyEventV2(event)
        if self._proxy_type == ProxyEventType.LambdaFunctionUrlEvent:
            logger.debug("Converting event to Lambda Function URL contract")
            return LambdaFunctionUrlEvent(event)
        logger.debug("Converting event to ALB contract")
        return ALBEvent(event)

    def _resolve(self) -> ResponseBuilder:
        """Resolves the response or return the not found response"""
        method = self.current_event.http_method.upper()
        path = self._remove_prefix(self.current_event.path)
        for route in self._routes:
            if method != route.method:
                continue
            match_results: Optional[Match] = route.rule.match(path)
            if match_results:
                logger.debug("Found a registered route. Calling function")
                return self._call_route(route, match_results.groupdict())  # pass fn args

        logger.debug(f"No match found for path {path} and method {method}")
        return self._not_found(method)

    def _remove_prefix(self, path: str) -> str:
        """Remove the configured prefix from the path"""
        if not isinstance(self._strip_prefixes, list):
            return path

        for prefix in self._strip_prefixes:
            if path == prefix:
                return "/"
            if self._path_starts_with(path, prefix):
                return path[len(prefix) :]

        return path

    @staticmethod
    def _path_starts_with(path: str, prefix: str):
        """Returns true if the `path` starts with a prefix plus a `/`"""
        if not isinstance(prefix, str) or prefix == "":
            return False

        return path.startswith(prefix + "/")

    def _not_found(self, method: str) -> ResponseBuilder:
        """Called when no matching route was found and includes support for the cors preflight response"""
        headers: Dict[str, Union[str, List[str]]] = {}
        if self._cors:
            logger.debug("CORS is enabled, updating headers.")
            headers.update(self._cors.to_dict())

            if method == "OPTIONS":
                logger.debug("Pre-flight request detected. Returning CORS with null response")
                headers["Access-Control-Allow-Methods"] = ",".join(sorted(self._cors_methods))
                return ResponseBuilder(Response(status_code=204, content_type=None, headers=headers, body=""))

        handler = self._lookup_exception_handler(NotFoundError)
        if handler:
            return ResponseBuilder(handler(NotFoundError()))

        return ResponseBuilder(
            Response(
                status_code=HTTPStatus.NOT_FOUND.value,
                content_type=content_types.APPLICATION_JSON,
                headers=headers,
                body=self._json_dump({"statusCode": HTTPStatus.NOT_FOUND.value, "message": "Not found"}),
            )
        )

    def _call_route(self, route: Route, args: Dict[str, str]) -> ResponseBuilder:
        """Actually call the matching route with any provided keyword arguments."""
        try:
            return ResponseBuilder(self._to_response(route.func(**args)), route)
        except Exception as exc:
            response_builder = self._call_exception_handler(exc, route)
            if response_builder:
                return response_builder

            if self._debug:
                # If the user has turned on debug mode,
                # we'll let the original exception propagate so
                # they get more information about what went wrong.
                return ResponseBuilder(
                    Response(
                        status_code=500,
                        content_type=content_types.TEXT_PLAIN,
                        body="".join(traceback.format_exc()),
                    ),
                    route,
                )

            raise

    def not_found(self, func: Optional[Callable] = None):
        if func is None:
            return self.exception_handler(NotFoundError)
        return self.exception_handler(NotFoundError)(func)

    def exception_handler(self, exc_class: Union[Type[Exception], List[Type[Exception]]]):
        def register_exception_handler(func: Callable):
            if isinstance(exc_class, list):
                for exp in exc_class:
                    self._exception_handlers[exp] = func
            else:
                self._exception_handlers[exc_class] = func
            return func

        return register_exception_handler

    def _lookup_exception_handler(self, exp_type: Type) -> Optional[Callable]:
        # Use "Method Resolution Order" to allow for matching against a base class
        # of an exception
        for cls in exp_type.__mro__:
            if cls in self._exception_handlers:
                return self._exception_handlers[cls]
        return None

    def _call_exception_handler(self, exp: Exception, route: Route) -> Optional[ResponseBuilder]:
        handler = self._lookup_exception_handler(type(exp))
        if handler:
            try:
                return ResponseBuilder(handler(exp), route)
            except ServiceError as service_error:
                exp = service_error

        if isinstance(exp, ServiceError):
            return ResponseBuilder(
                Response(
                    status_code=exp.status_code,
                    content_type=content_types.APPLICATION_JSON,
                    body=self._json_dump({"statusCode": exp.status_code, "message": exp.msg}),
                ),
                route,
            )

        return None

    def _to_response(self, result: Union[Dict, Tuple, Response]) -> Response:
        """Convert the route's result to a Response

         3 main result types are supported:

        - Dict[str, Any]: Rest api response with just the Dict to json stringify and content-type is set to
          application/json
        - Tuple[dict, int]: Same dict handling as above but with the option of including a status code
        - Response: returned as is, and allows for more flexibility
        """
        status_code = HTTPStatus.OK
        if isinstance(result, Response):
            return result
        elif isinstance(result, tuple) and len(result) == 2:
            # Unpack result dict and status code from tuple
            result, status_code = result

        logger.debug("Simple response detected, serializing return before constructing final response")
        return Response(
            status_code=status_code,
            content_type=content_types.APPLICATION_JSON,
            body=self._json_dump(result),
        )

    def _json_dump(self, obj: Any) -> str:
        return self._serializer(obj)

    def include_router(self, router: "Router", prefix: Optional[str] = None) -> None:
        """Adds all routes and context defined in a router

        Parameters
        ----------
        router : Router
            The Router containing a list of routes to be registered after the existing routes
        prefix : str, optional
            An optional prefix to be added to the originally defined rule
        """

        # Add reference to parent ApiGatewayResolver to support use cases where people subclass it to add custom logic
        router.api_resolver = self

        # Merge app and router context
        self.context.update(**router.context)
        # use pointer to allow context clearance after event is processed e.g., resolve(evt, ctx)
        router.context = self.context

        for route, func in router._routes.items():
            if prefix:
                rule = route[0]
                rule = prefix if rule == "/" else f"{prefix}{rule}"
                route = (rule, *route[1:])

            self.route(*route)(func)


class Router(BaseRouter):
    """Router helper class to allow splitting ApiGatewayResolver into multiple files"""

    def __init__(self):
        self._routes: Dict[tuple, Callable] = {}
        self.api_resolver: Optional[BaseRouter] = None
        self.context = {}  # early init as customers might add context before event resolution

    def route(
        self,
        rule: str,
        method: Union[str, Union[List[str], Tuple[str]]],
        cors: Optional[bool] = None,
        compress: bool = False,
        cache_control: Optional[str] = None,
    ):
        def register_route(func: Callable):
            # Convert methods to tuple. It needs to be hashable as its part of the self._routes dict key
            methods = (method,) if isinstance(method, str) else tuple(method)
            self._routes[(rule, methods, cors, compress, cache_control)] = func
            return func

        return register_route


class APIGatewayRestResolver(ApiGatewayResolver):
    current_event: APIGatewayProxyEvent

    def __init__(
        self,
        cors: Optional[CORSConfig] = None,
        debug: Optional[bool] = None,
        serializer: Optional[Callable[[Dict], str]] = None,
        strip_prefixes: Optional[List[str]] = None,
    ):
        """Amazon API Gateway REST and HTTP API v1 payload resolver"""
        super().__init__(ProxyEventType.APIGatewayProxyEvent, cors, debug, serializer, strip_prefixes)

    # override route to ignore trailing "/" in routes for REST API
    def route(
        self,
        rule: str,
        method: Union[str, Union[List[str], Tuple[str]]],
        cors: Optional[bool] = None,
        compress: bool = False,
        cache_control: Optional[str] = None,
    ):
        # NOTE: see #1552 for more context.
        return super().route(rule.rstrip("/"), method, cors, compress, cache_control)

    # Override _compile_regex to exclude trailing slashes for route resolution
    @staticmethod
    def _compile_regex(rule: str, base_regex: str = _ROUTE_REGEX):
        return super(APIGatewayRestResolver, APIGatewayRestResolver)._compile_regex(rule, "^{}/*$")


class APIGatewayHttpResolver(ApiGatewayResolver):
    current_event: APIGatewayProxyEventV2

    def __init__(
        self,
        cors: Optional[CORSConfig] = None,
        debug: Optional[bool] = None,
        serializer: Optional[Callable[[Dict], str]] = None,
        strip_prefixes: Optional[List[str]] = None,
    ):
        """Amazon API Gateway HTTP API v2 payload resolver"""
        super().__init__(ProxyEventType.APIGatewayProxyEventV2, cors, debug, serializer, strip_prefixes)


class ALBResolver(ApiGatewayResolver):
    current_event: ALBEvent

    def __init__(
        self,
        cors: Optional[CORSConfig] = None,
        debug: Optional[bool] = None,
        serializer: Optional[Callable[[Dict], str]] = None,
        strip_prefixes: Optional[List[str]] = None,
    ):
        """Amazon Application Load Balancer (ALB) resolver"""
        super().__init__(ProxyEventType.ALBEvent, cors, debug, serializer, strip_prefixes)
