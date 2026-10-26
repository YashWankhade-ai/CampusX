FROM nginx:alpine

# Copy static frontend assets into Nginx web root
COPY . /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
