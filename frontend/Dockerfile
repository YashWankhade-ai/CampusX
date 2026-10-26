FROM nginx:alpine

# Replace default Nginx configuration with CampusX reverse proxy gateway
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Verify Nginx configuration syntax during build
RUN nginx -t

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
